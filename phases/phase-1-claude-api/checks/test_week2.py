"""Week 2 checks: the three tools and the model loop.

Run them with `make check WEEK=2`. They use the fake Claude API on localhost,
so they are free. Postgres must run (`make up`), because the tools read it.
"""

from __future__ import annotations

import json

import pytest

from labkit.fake_claude import answer_reply, tool_reply, tool_results
from labkit.sse import ask

QUESTION = "Which datasets are about crude oil production?"
FINAL = "The dataset saudi-crude-oil-production-from-sama-annual-statistics-2015-dec fits."
CRUDE_OIL = "saudi-crude-oil-production-from-sama-annual-statistics-2015-dec"
TOOL_NAMES = {"search_datasets", "get_dataset_schema", "get_dataset_stats"}


def assistant_blocks(body, index=1):
    content = body["messages"][index]["content"]
    assert not isinstance(content, str), "The assistant turn must keep its content blocks."
    return content


# ---- step 2: the tools ------------------------------------------------------------


def test_the_three_tools_are_defined():
    from assistant.tools import TOOLS

    # Later phases add tools, so the check accepts more than these three.
    assert TOOL_NAMES <= {tool["name"] for tool in TOOLS}
    for tool in TOOLS:
        assert len(tool["description"]) >= 150, (
            f"{tool['name']}: the description is the main thing that the model reads to choose "
            "a tool. Write 3 or 4 sentences: what the tool does, when to use it, what it returns."
        )
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert schema.get("required"), f"{tool['name']}: list the required properties."
        for name in schema["required"]:
            assert name in schema["properties"]
            assert schema["properties"][name].get("description"), (
                f"{tool['name']}: describe the property {name}."
            )
    by_name = {tool["name"]: tool for tool in TOOLS}
    assert "query" in by_name["search_datasets"]["input_schema"]["required"]
    assert by_name["get_dataset_schema"]["input_schema"]["required"] == ["dataset_id"]
    assert by_name["get_dataset_stats"]["input_schema"]["required"] == ["dataset_id"]


def test_search_datasets_finds_datasets(database):
    from assistant.tools import run_tool

    output = run_tool("search_datasets", {"query": "crude oil production"})
    assert isinstance(output, str), "run_tool returns a JSON string."
    json.loads(output)
    assert CRUDE_OIL in output, "A search for 'crude oil production' must return the Crude Oil Production dataset."


def test_search_datasets_returns_few_rows(database, catalogue):
    from assistant.tools import run_tool

    output = run_tool("search_datasets", {"query": "electricity"})
    found = [dataset["id"] for dataset in catalogue if f'"{dataset["id"]}"' in output]
    assert 1 <= len(found) <= 20, (
        "Return the best matches only. A tool result goes into the prompt, and you pay for "
        "each token of it."
    )


def test_get_dataset_schema_returns_each_column(database, catalogue):
    from assistant.tools import run_tool

    dataset = next(d for d in catalogue if d["id"] == CRUDE_OIL)
    output = run_tool("get_dataset_schema", {"dataset_id": CRUDE_OIL})
    json.loads(output)
    for column in dataset["columns"]:
        assert column["name"] in output, f"The column {column['name']} is not in the result."


def test_get_dataset_stats_returns_the_facts(database, catalogue):
    from assistant.tools import run_tool

    dataset = next(d for d in catalogue if d["id"] == CRUDE_OIL)
    output = run_tool("get_dataset_stats", {"dataset_id": CRUDE_OIL})
    json.loads(output)
    assert str(dataset["records_count"]) in output, "The stats must give the number of records."
    assert dataset["updated_at"][:10] in output, "The stats must give the date of the last update."


def test_a_wrong_tool_call_raises_an_error(database):
    from assistant.tools import run_tool

    with pytest.raises(Exception) as unknown_tool:
        run_tool("delete_dataset", {"dataset_id": CRUDE_OIL})
    assert not isinstance(unknown_tool.value, NotImplementedError)
    with pytest.raises(Exception) as unknown_dataset:
        run_tool("get_dataset_schema", {"dataset_id": "no-such-dataset"})
    assert str(unknown_dataset.value), "Give the exception a message. The model reads it."


# ---- step 3: the loop ---------------------------------------------------------------


def test_the_loop_runs_a_tool_and_sends_the_result_back(client, fake, database):
    call = tool_reply(("search_datasets", {"query": "crude oil production"}))
    fake.script(call, answer_reply(FINAL))
    result = ask(client, QUESTION)

    assert len(fake.requests) == 2, "One request asks for the tool. The next request holds its result."
    first, second = fake.requests
    assert TOOL_NAMES <= {tool["name"] for tool in first["tools"]}, "Send the tool definitions."
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]

    sent_back = assistant_blocks(second)
    tool_use = call.content[-1]
    assert any(b.get("type") == "tool_use" and b.get("id") == tool_use["id"] for b in sent_back), (
        "Add the complete assistant turn to the messages, with its tool_use block."
    )
    thinking = call.content[0]
    assert any(
        b.get("type") == "thinking" and b.get("signature") == thinking["signature"] for b in sent_back
    ), (
        "Send the thinking block of the assistant turn back unchanged. The docs say that you "
        "must pass thinking blocks back when you return tool results."
    )

    results = tool_results(second)
    assert len(results) == 1
    assert results[0]["tool_use_id"] == tool_use["id"]
    assert not results[0].get("is_error")
    content = results[0]["content"]
    content = content if isinstance(content, str) else content[0]["text"]
    assert CRUDE_OIL in content, "The tool result must hold the output of search_datasets."

    assert result.tools == [
        {"name": "search_datasets", "input": {"query": "crude oil production"}, "is_error": False}
    ], "Send one `tool` event for each tool call, with name, input and is_error."
    assert result.text == FINAL
    assert result.done["requests"] == 2
    assert result.done["stop"] == "final"


def test_done_adds_the_usage_of_each_request(client, fake, database):
    fake.script(
        tool_reply(("search_datasets", {"query": "oil"}), usage={"input_tokens": 1000, "output_tokens": 100}),
        answer_reply(FINAL, usage={"input_tokens": 1500, "output_tokens": 200}),
    )
    done = ask(client, QUESTION).done

    assert done["input_tokens"] == 2500
    assert done["output_tokens"] == 300
    assert done["cost_usd"] == pytest.approx((2500 * 0.10 + 300 * 0.50) / 1_000_000)


def test_two_tool_calls_in_one_turn_get_two_results_in_one_message(client, fake, database):
    call = tool_reply(
        ("get_dataset_schema", {"dataset_id": CRUDE_OIL}),
        ("get_dataset_stats", {"dataset_id": CRUDE_OIL}),
    )
    fake.script(call, answer_reply(FINAL))
    result = ask(client, QUESTION)

    assert len(fake.requests) == 2, "Run each tool of the turn, then send one request with all results."
    results = tool_results(fake.requests[1])
    wanted = [block["id"] for block in call.content if block["type"] == "tool_use"]
    assert [r["tool_use_id"] for r in results] == wanted, (
        "Put the results of all tool calls of one turn in one user message."
    )
    assert [tool["name"] for tool in result.tools] == ["get_dataset_schema", "get_dataset_stats"]


def test_an_unknown_tool_gives_an_error_result_and_the_loop_continues(client, fake, database):
    fake.script(tool_reply(("delete_dataset", {"dataset_id": CRUDE_OIL})), answer_reply(FINAL))
    result = ask(client, QUESTION)

    assert len(fake.requests) == 2, "A tool error must not stop the loop."
    results = tool_results(fake.requests[1])
    assert results[0].get("is_error") is True, "Mark the tool result with is_error: true."
    assert results[0]["content"], "Give the model the error message, so it can correct the call."
    assert result.tools[0]["is_error"] is True
    assert result.done["stop"] == "final"


def test_a_broken_tool_does_not_stop_the_loop(client, fake, monkeypatch):
    # Nothing listens on port 9 of localhost, so each tool fails when it reads the database.
    monkeypatch.setenv("DATABASE_URL", "postgresql://assistant:assistant@127.0.0.1:9/assistant")
    fake.script(tool_reply(("search_datasets", {"query": "oil"})), answer_reply("The catalogue is not available."))
    result = ask(client, QUESTION)

    assert result.status_code == 200
    assert len(fake.requests) == 2, "Catch the exception of the tool and send it to the model."
    assert tool_results(fake.requests[1])[0].get("is_error") is True
    assert result.done["stop"] == "final"


def test_the_loop_stops_after_8_turns(client, fake, database):
    fake.always(lambda body: tool_reply(("search_datasets", {"query": "oil"})))
    result = ask(client, QUESTION)

    assert len(fake.requests) == 8, "Stop after 8 requests to the model (get_settings().max_turns)."
    assert result.done["stop"] == "max_turns"
    assert result.done["requests"] == 8
