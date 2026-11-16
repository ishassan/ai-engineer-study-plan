"""Week 12 checks: the conversation, compaction and the long-term memory, by hand.

Run them with `make check WEEK=12`. They use the fake Claude API on localhost, so they are
free. Postgres and the embedding service must run (`make up`). The checks use the
hand-written loop (AGENT_IMPL=handwritten).
"""

from __future__ import annotations

import json
import uuid

import pytest
from phase4_helpers import ask, has_tools, new_user, prompt_size, prompt_text, saved_facts

from labkit.fake_claude import _prompt_blocks, json_reply, text_reply, tool_reply

FACT = "The user works in the water team and only uses datasets that are updated monthly."
FACT_QUESTION = "Which water datasets that are updated monthly can my team use?"


@pytest.fixture(autouse=True)
def handwritten(monkeypatch):
    monkeypatch.setenv("AGENT_IMPL", "handwritten")
    monkeypatch.setenv("AGENT_PLANNER", "off")


def long_answer(body: dict, marker: str = "") -> object:
    """A final answer of about 1,800 characters, so the conversation grows fast."""
    text = f"Answer {marker}. " + "The catalogue has datasets about water use by region and year. " * 28
    return json_reply({"answer": text, "dataset_ids": [], "tools_called": []})


# ---- step 1: the conversation --------------------------------------------------------------


def test_the_migration_made_the_tables(tables, sql):
    columns = {
        (row["table_name"], row["column_name"]): row["udt_name"]
        for row in sql(
            "SELECT table_name, column_name, udt_name FROM information_schema.columns "
            "WHERE table_name IN ('conversations', 'conversation_messages', 'memories')"
        )
    }
    assert columns[("memories", "embedding")] == "vector"
    assert columns[("memories", "user_id")] == "text"
    assert columns[("conversation_messages", "content")] == "jsonb"


def test_each_stream_reports_its_conversation(client, fake, tables):
    first = ask(client, "What is a dataset?")
    conversation_id = first.done.get("conversation_id")
    assert conversation_id, "The `done` event must hold the conversation_id (the given api.py adds it)."
    again = ask(client, "And what is a column?", conversation_id=conversation_id)
    assert again.done.get("conversation_id") == conversation_id
    other = ask(client, "What is a dataset?")
    assert other.done.get("conversation_id") not in {None, conversation_id}, "A request without an ID starts a new conversation."


def test_a_conversation_keeps_its_history(client, fake, tables):
    marker = uuid.uuid4().hex[:8]
    fake.script(json_reply({"answer": f"The dataset is water-use-{marker}.", "dataset_ids": [], "tools_called": []}))
    first = ask(client, f"Which dataset covers water use? (case {marker})", user="history-check")
    second = ask(client, "Who owns it?", user="history-check", conversation_id=first.done["conversation_id"])

    assert second.answer is not None, second.errors
    text = prompt_text(fake.requests[-1])
    assert f"(case {marker})" in text, "The request of the second question must hold the first question."
    assert f"water-use-{marker}" in text, "The request of the second question must hold the first answer."
    assert ask(client, "Who owns it?", user="history-check").done is not None
    assert f"(case {marker})" not in prompt_text(fake.requests[-1]), "A new conversation starts empty."


def test_another_user_cannot_read_a_conversation(client, fake, tables):
    marker = uuid.uuid4().hex[:8]
    first = ask(client, f"My secret project is {marker}. Which datasets help?", user=new_user())
    fake.reset()
    stolen = ask(client, "What is my secret project?", user=new_user(), conversation_id=first.done["conversation_id"])

    assert all(marker not in prompt_text(body) for body in fake.requests), (
        "Another user sent the conversation ID of the first user, and the model got the messages "
        "of the first user. Check the user of the conversation before you load its messages."
    )
    assert stolen.answer is None or stolen.errors, "Refuse the request: send an `error` event."


# ---- step 2: compaction --------------------------------------------------------------------


def test_a_long_conversation_is_compacted_and_continues(client, fake, tables, monkeypatch):
    # Measure the size of a first request (system prompt and tools) with the fake API.
    ask(client, "What is a dataset?", user=new_user())
    baseline = sum(tokens for _, tokens, _ in _prompt_blocks(fake.requests[0]))
    fake.reset()
    monkeypatch.setenv("COMPACT_AT_TOKENS", str(baseline + 1000))

    summary = f"SUMMARY-{uuid.uuid4().hex[:8]}: the user asked five questions about water datasets."
    kinds: list[str] = []

    def reply(body):
        if not has_tools(body):
            kinds.append("summary")
            return text_reply(summary)
        kinds.append("agent")
        return long_answer(body)

    fake.always(reply)
    user, conversation_id = new_user(), None
    results = []
    for n in range(1, 6):
        result = ask(client, f"Question Q{n}-mark: which water datasets cover region {n}?", user=user,
                     conversation_id=conversation_id)
        conversation_id = result.done.get("conversation_id")
        results.append(result)

    assert all(result.answer is not None for result in results), [r.errors for r in results]
    assert "summary" in kinds, (
        f"No summary request in a conversation of five long turns, with COMPACT_AT_TOKENS={baseline + 1000}. "
        "Count the whole prompt: input tokens plus the cache reads and the cache writes, plus the output "
        "tokens. A summary request is a request without tools."
    )
    position = kinds.index("summary")
    assert kinds[:position].count("agent") <= 4, (
        "The context passed the limit at the third question, but the summary came after the fourth. "
        "Count the cache reads too: the system prompt and the tools are in the cache."
    )
    summary_request = fake.requests[position]
    assert "Q1-mark" in prompt_text(summary_request), "The summary request must hold the old messages."
    assert position + 1 < len(fake.requests), "The conversation must go on after the summary."
    before, after = fake.requests[position - 1], fake.requests[position + 1]
    assert summary in prompt_text(after), "The first request after compaction must hold the summary."
    assert prompt_size(after) < prompt_size(before), "The request after compaction must be shorter than the one before."
    assert "Q1-mark" not in prompt_text(after), "After compaction the old messages are not in the request."


# ---- step 3: long-term memory --------------------------------------------------------------


def test_the_save_memory_tool_is_defined():
    from assistant.tools import TOOLS

    tool = next((tool for tool in TOOLS if tool["name"] == "save_memory"), None)
    assert tool is not None, "Add the tool save_memory to TOOLS."
    assert tool["input_schema"]["required"] == ["fact"]
    assert len(tool["description"]) >= 150, "Say when the model saves a fact, and what makes a good fact."


def test_search_facts_finds_the_closest_fact_of_the_user(tables, embeddings):
    from assistant.memory import save_fact, search_facts

    user, other = new_user(), new_user()
    save_fact(user, "The user wants each answer in Arabic.")
    save_fact(user, "The user works on electricity statistics for the regulator.")
    save_fact(other, "The user works on electricity prices in Riyadh.")

    best = search_facts(user, "Which electricity datasets help my work?", 1)
    assert [fact["text"] for fact in best] == ["The user works on electricity statistics for the regulator."]
    found = [fact["text"] for fact in search_facts(user, "electricity", 10)]
    assert "The user works on electricity prices in Riyadh." not in found, "Search only the facts of the user."
    assert len(found) == 2
    assert search_facts(new_user(), "electricity", 10) == [], "A user without facts gets an empty list."


def test_a_fact_saved_in_one_conversation_reaches_the_next_one(client, fake, sql, tables, embeddings):
    user = new_user()
    fake.script(
        tool_reply(("save_memory", {"fact": FACT})),
        json_reply({"answer": "I will remember that.", "dataset_ids": [], "tools_called": ["save_memory"]}),
    )
    first = ask(client, "I work in the water team, and we only use datasets that are updated monthly.", user=user)
    assert [tool["name"] for tool in first.tools] == ["save_memory"]
    assert first.tools[0]["is_error"] is False, first.tools
    assert saved_facts(sql, user) == [{"text": FACT, "has_vector": True}], "Store the fact with its vector and the user."

    fake.reset()
    second = ask(client, FACT_QUESTION, user=user)
    assert second.answer is not None
    assert FACT in prompt_text(fake.requests[0]), (
        "The second conversation of the same user must give the saved fact to the model, in the "
        "first request. Search the facts of the user with the question."
    )


def test_a_fact_does_not_reach_another_user(client, fake, tables, embeddings):
    from assistant.memory import save_fact

    owner = new_user()
    marker = uuid.uuid4().hex[:8]
    save_fact(owner, f"The user leads the project {marker} on monthly water data.")
    ask(client, FACT_QUESTION, user=new_user())
    ask(client, FACT_QUESTION)

    assert fake.requests, "No request reached the fake API."
    assert all(marker not in json.dumps(body) for body in fake.requests), "A fact of one user reached another user."
