"""Week 15 checks: the checkpointer, the store, approval of register_dataset, and the audit log.

Run them with `make check WEEK=15`. They use the fake Claude API on localhost, so they are
free. Postgres and the embedding service must run (`make up`). The checks use the graph
(AGENT_IMPL=langgraph). One check starts your API as a real process with uvicorn, stops it
in the middle of a conversation and starts it again.

The checks add datasets with IDs that start with `check-` to the catalogue, and delete them
at the end. The rows in audit_log, in the checkpoint tables and in the store stay.
"""

from __future__ import annotations

import json
import uuid

import pytest
from phase4_helpers import approve, ask, new_user, prompt_text, saved_facts, tool_calls, tool_results

from labkit.fake_claude import json_reply, tool_reply

BAD_ID = "no-such-dataset-for-the-check"
REFUSAL_WORDS = ("refus", "reject", "denied", "declin", "not approved")


@pytest.fixture(autouse=True)
def graph(monkeypatch):
    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("AGENT_PLANNER", "off")
    monkeypatch.setenv("PROVIDER", "anthropic")


@pytest.fixture
def new_dataset(sql):
    """The arguments of a register_dataset call for a new dataset. The row is deleted at the end."""
    dataset_id = f"check-{uuid.uuid4().hex[:10]}"
    arguments = {
        "dataset_id": dataset_id,
        "title": f"Check dataset {dataset_id}",
        "description": "A dataset that a check of week 15 registers. The check deletes it at the end.",
        "owner": "Lab checks",
    }
    yield arguments
    sql("DELETE FROM datasets WHERE id = %s", (dataset_id,))


def answer(text: str, tools: list[str] | None = None):
    return json_reply({"answer": text, "dataset_ids": [], "tools_called": tools or []})


def dataset_rows(sql, dataset_id: str) -> list[dict]:
    return sql("SELECT id, title, owner FROM datasets WHERE id = %s", (dataset_id,))


def audit_rows(sql, conversation_id: str) -> list[dict]:
    return sql(
        "SELECT user_id, tool, arguments, result, approval, approver FROM audit_log "
        "WHERE conversation_id = %s ORDER BY id",
        (conversation_id,),
    )


def result_for(body: dict, name: str) -> dict | None:
    """The tool result of the call of `name` in a request."""
    ids = [call["id"] for call in tool_calls(body) if call["name"] == name]
    return next((result for result in tool_results(body) if result["id"] in ids), None)


def waits_for_approval(result, arguments: dict) -> None:
    assert result.status_code == 200, result.status_code
    approvals = [data for event, data in result.events if event == "approval"]
    assert approvals, (
        "The graph must pause before register_dataset: send an `approval` event (the tool and its "
        f"arguments) and end the stream with `done`. Events: {result.names}, errors: {result.errors}"
    )
    assert approvals[0].get("name") == "register_dataset", approvals[0]
    assert approvals[0].get("input") == arguments, "The approval event holds the arguments of the call (`input`)."
    assert result.answer is None, "While the graph waits for an approval, the stream has no answer."
    assert result.done is not None, "End the stream with `done` when the graph pauses."


# ---- step 2: the checkpointer and the store ------------------------------------------------


def test_the_graph_saves_each_conversation_with_the_postgres_checkpointer(client, fake, sql, database):
    fake.script(answer("A dataset is a table of records."))
    result = ask(client, "What is a dataset?", user=new_user())
    conversation_id = result.done.get("conversation_id")
    assert result.answer is not None, result.errors
    found = {row["name"] for row in sql("SELECT to_regclass(name)::text AS name FROM unnest(%s::text[]) AS name",
                                         (["checkpoints", "checkpoint_blobs", "checkpoint_writes"],)) if row["name"]}
    assert found == {"checkpoints", "checkpoint_blobs", "checkpoint_writes"}, (
        "The tables of PostgresSaver do not exist. Call setup() of the checkpointer one time."
    )
    rows = sql("SELECT count(*) AS n FROM checkpoints WHERE thread_id = %s", (conversation_id,))
    assert rows[0]["n"] > 0, "Compile the graph with the PostgresSaver, and use the conversation_id as thread_id."


def test_a_fact_is_saved_in_the_postgres_store(sql, tables, embeddings):
    from assistant.memory import save_fact, search_facts

    user, fact = new_user(), f"The user reviews the cement statistics every quarter ({uuid.uuid4().hex[:6]})."
    save_fact(user, fact)
    assert sql("SELECT to_regclass('store') IS NOT NULL AS found")[0]["found"], (
        "The table `store` of PostgresStore does not exist. Call setup() of the store one time."
    )
    assert sql("SELECT count(*) AS n FROM memories WHERE user_id = %s", (user,))[0]["n"] == 0, (
        "Save the facts in the PostgresStore now, not in the table memories."
    )
    assert saved_facts(sql, user) == [{"text": fact, "has_vector": True}], (
        "The store must hold the fact as {'text': ...} in a namespace with the user, with its vector "
        "(an index with the embedding function of Phase 2)."
    )
    assert [item["text"] for item in search_facts(user, "cement statistics", 3)] == [fact]


# ---- step 3: approval of register_dataset --------------------------------------------------


def test_the_conversation_continues_after_a_restart_of_the_service(service, fake, sql, new_dataset, database):
    marker = uuid.uuid4().hex[:8]
    question = f"Please register the dataset of the case {marker} in the catalogue."
    fake.script(
        tool_reply(("register_dataset", new_dataset)),
        answer(f"The dataset is registered (case {marker}).", ["register_dataset"]),
        answer("You asked me to register one dataset.", []),
    )
    user = new_user()
    service.start()
    first = ask(service.client, question, user=user)
    waits_for_approval(first, new_dataset)
    conversation_id = first.done["conversation_id"]
    assert dataset_rows(sql, new_dataset["dataset_id"]) == [], "register_dataset ran before the approval."

    service.kill()
    service.start()
    before = len(fake.requests)
    resumed = approve(service.client, conversation_id, True, user="check-approver")
    assert resumed.status_code == 200, resumed.status_code
    assert resumed.answer is not None, (
        "After a restart of the service, POST /approve must continue the conversation from the pause. "
        f"Events: {resumed.names}, errors: {resumed.errors}"
    )
    new = fake.requests[before:]
    assert len(new) == 1, (
        f"After the approval the graph sent {len(new)} requests to the model, not 1. It must continue "
        "from its last step (the tool call), not start the question again."
    )
    assert question in prompt_text(new[0]), "The request after the restart must hold the question."
    output = result_for(new[0], "register_dataset")
    assert output is not None and not output["is_error"], (
        "The request after the restart must hold the result of register_dataset, with the ID of the call "
        "from before the restart."
    )
    assert dataset_rows(sql, new_dataset["dataset_id"]) == [
        {"id": new_dataset["dataset_id"], "title": new_dataset["title"], "owner": new_dataset["owner"]}
    ], "After the approval, register_dataset adds the dataset to the table datasets."

    service.kill()
    service.start()
    again = ask(service.client, "What did I ask you to do?", user=user, conversation_id=conversation_id)
    assert again.answer is not None, again.errors
    text = prompt_text(fake.requests[-1])
    assert question in text and f"case {marker}" in text, (
        "After a second restart, the next question of the conversation must hold the earlier messages."
    )


def test_register_dataset_does_not_run_after_a_refusal(client, fake, sql, new_dataset, database):
    fake.script(
        tool_reply(("register_dataset", new_dataset)),
        answer("The person refused the action, so the dataset was not registered.", ["register_dataset"]),
    )
    first = ask(client, "Register this dataset for me, please.", user=new_user())
    waits_for_approval(first, new_dataset)
    assert dataset_rows(sql, new_dataset["dataset_id"]) == [], "register_dataset ran before the approval."

    before = len(fake.requests)
    refused = approve(client, first.done["conversation_id"], False, user="check-approver")
    assert refused.answer is not None, f"After a refusal the model answers. Errors: {refused.errors}"
    assert dataset_rows(sql, new_dataset["dataset_id"]) == [], "register_dataset ran after a refusal."
    assert len(fake.requests) == before + 1
    output = result_for(fake.requests[-1], "register_dataset")
    assert output is not None, "Send the refusal to the model as the tool result of the call."
    assert any(word in output["output"].lower() for word in REFUSAL_WORDS), (
        f"The tool result must say that a person refused the action: {output['output']!r}"
    )


# ---- step 4: the audit log -----------------------------------------------------------------


def test_each_tool_call_has_one_row_in_the_audit_log(client, fake, sql, new_dataset, database):
    search = {"query": "cement production"}
    schema = {"dataset_id": BAD_ID}
    fake.script(
        tool_reply(("search_datasets", search), ("get_dataset_schema", schema)),
        tool_reply(("register_dataset", new_dataset)),
        answer("The dataset is registered.", ["search_datasets", "get_dataset_schema", "register_dataset"]),
    )
    user = new_user()
    first = ask(client, "Find the cement datasets, and register a new one.", user=user)
    waits_for_approval(first, new_dataset)
    conversation_id = first.done["conversation_id"]
    rows = audit_rows(sql, conversation_id)
    assert [row["tool"] for row in rows] == ["search_datasets", "get_dataset_schema"], (
        f"Before the approval, the audit log holds the two calls that ran: {[row['tool'] for row in rows]}"
    )
    done = approve(client, conversation_id, True, user="check-approver")
    assert done.answer is not None, done.errors

    rows = audit_rows(sql, conversation_id)
    assert [row["tool"] for row in rows] == ["search_datasets", "get_dataset_schema", "register_dataset"], (
        "Write one row to audit_log for each tool call, in the order of the calls."
    )
    assert all(row["user_id"] == user for row in rows), "user_id is the user who asked (X-User of /ask)."
    assert [row["arguments"] for row in rows] == [search, schema, new_dataset]
    assert [(row["approval"], row["approver"]) for row in rows] == [
        ("not_needed", None), ("not_needed", None), ("approved", "check-approver"),
    ], "The approval is not_needed or the decision, and the approver is the user of /approve."
    assert all(row["result"] for row in rows), "Write the result that went back to the model."
    assert BAD_ID in rows[1]["result"] or "No dataset" in rows[1]["result"], (
        f"The row of a failed call holds the error: {rows[1]['result']!r}"
    )
    assert json.dumps(rows[0]["arguments"]) and rows[2]["result"] != rows[1]["result"]


def test_a_refusal_is_in_the_audit_log(client, fake, sql, new_dataset, database):
    fake.script(tool_reply(("register_dataset", new_dataset)), answer("The action was refused."))
    user = new_user()
    first = ask(client, "Register this dataset for me, please.", user=user)
    waits_for_approval(first, new_dataset)
    assert audit_rows(sql, first.done["conversation_id"]) == [], "Write the row when the call ends or is refused."
    approve(client, first.done["conversation_id"], False, user="check-approver")
    rows = audit_rows(sql, first.done["conversation_id"])
    assert len(rows) == 1, rows
    assert (rows[0]["tool"], rows[0]["user_id"], rows[0]["approval"], rows[0]["approver"]) == (
        "register_dataset", user, "refused", "check-approver"
    )
    assert any(word in rows[0]["result"].lower() for word in REFUSAL_WORDS), rows[0]["result"]
