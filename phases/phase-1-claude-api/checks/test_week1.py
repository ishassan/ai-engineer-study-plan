"""Week 1 checks: the first request, the stream, the cost log, the response cache
and the test questions.

Run them with `make check WEEK=1`. They use the fake Claude API on localhost,
so they are free.
"""

from __future__ import annotations

import pytest

from labkit.fake_claude import answer_reply, first_user_text
from labkit.sse import ask

QUESTION = "Which datasets are about crude oil production?"
OTHER_QUESTION = "Which dataset has the length of roads?"
REPLY = "Two datasets in the catalogue are about crude oil production in the Kingdom."

LOG_FIELDS = {"model", "input_tokens", "output_tokens", "cost_usd", "latency_ms", "replayed"}


# ---- step 2: the catalogue ----------------------------------------------------


def test_the_catalogue_is_in_postgres(database):
    """`make up` started Postgres and loaded the 50 datasets."""


# ---- step 4: /ask streams the answer and logs the request --------------------------


def test_ask_streams_the_answer_as_events(client, fake):
    fake.script(answer_reply(REPLY))
    result = ask(client, QUESTION)

    assert result.status_code == 200
    assert result.content_type.startswith("text/event-stream")
    assert result.text == REPLY, "The text events together must give the full answer of the model."
    if result.answer is None:  # Before week 3, the answer arrives as text events.
        assert len(result.of("text")) >= 2, (
            "Send each piece of text as its own `text` event when it arrives. "
            "Do not wait for the full answer."
        )
    assert result.done  # The stream ends with a `done` event.


def test_the_request_to_claude_is_correct(client, fake):
    ask(client, QUESTION)
    body = fake.last_request

    assert body["model"] == "claude-haiku-5-5"
    assert QUESTION in first_user_text(body), "The first user message must hold the question."
    assert body.get("stream") is True, "Use client.messages.stream(), so the text arrives in pieces."
    assert body["max_tokens"] >= 1024, (
        "On Haiku 5.5, thinking is on by default and counts toward max_tokens. "
        "Leave room for it: use get_settings().max_tokens."
    )
    for name in ("temperature", "top_p", "top_k"):
        assert name not in body, f"The model page of Haiku 5.5 says to omit {name}."


def test_done_reports_tokens_cost_and_latency(client, fake):
    fake.script(answer_reply(REPLY, usage={"input_tokens": 1200, "output_tokens": 300}))
    done = ask(client, QUESTION).done

    assert done["model"] == "claude-haiku-5-5"
    assert done["input_tokens"] == 1200
    assert done["output_tokens"] == 300
    # $0.10 for each million input tokens and $0.50 for each million output tokens.
    assert done["cost_usd"] == pytest.approx((1200 * 0.10 + 300 * 0.50) / 1_000_000)
    assert done["latency_ms"] > 0


def test_each_request_is_in_the_request_log(client, fake, request_log):
    fake.script(answer_reply(REPLY, usage={"input_tokens": 1200, "output_tokens": 300}))
    ask(client, QUESTION)
    lines = request_log()

    assert len(lines) == 1, "Write one log line for each request to Claude."
    line = lines[0]
    assert LOG_FIELDS <= set(line), f"The log line needs the fields {sorted(LOG_FIELDS - set(line))}."
    assert line["model"] == "claude-haiku-5-5"
    assert (line["input_tokens"], line["output_tokens"]) == (1200, 300)
    assert line["cost_usd"] == pytest.approx((1200 * 0.10 + 300 * 0.50) / 1_000_000)
    assert line["latency_ms"] > 0
    assert line["replayed"] is False


def test_cost_usd_uses_the_price_table():
    from anthropic.types import Usage

    from assistant.llm import cost_usd

    usage = Usage(input_tokens=2_000_000, output_tokens=1_000_000)
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(2 * 0.10 + 1 * 0.50)


# ---- step 5: the response cache ---------------------------------------------------


def test_request_hash_ignores_the_order_of_the_keys():
    from assistant.llm import request_hash

    one = {"model": "claude-haiku-5-5", "max_tokens": 100, "messages": [{"role": "user", "content": "a"}]}
    two = {"messages": [{"content": "a", "role": "user"}], "max_tokens": 100, "model": "claude-haiku-5-5"}
    assert request_hash(one) == request_hash(two), "Sort the keys before you make the hash."


def test_request_hash_changes_when_any_part_of_the_request_changes():
    from assistant.llm import request_hash

    base = {"model": "claude-haiku-5-5", "max_tokens": 100, "messages": [{"role": "user", "content": "a"}]}
    assert request_hash(base) != request_hash(dict(base, max_tokens=200))
    assert request_hash(base) != request_hash(dict(base, system="Be brief."))
    assert request_hash(base) != request_hash(
        dict(base, messages=[{"role": "user", "content": "b"}])
    )


def test_the_same_question_twice_makes_one_api_call(client, fake, cache_files, request_log):
    fake.script(answer_reply(REPLY, usage={"input_tokens": 1200, "output_tokens": 300}))
    first = ask(client, QUESTION)
    second = ask(client, QUESTION)

    assert len(fake.requests) == 1, "The second request must come from the response cache."
    assert second.text == first.text == REPLY, "A replay gives the saved answer of the model."
    assert len(cache_files()) == 1, "Save each response in one file under get_settings().response_cache_dir."
    assert second.done["cost_usd"] == 0, "A replayed answer costs nothing."

    lines = request_log()
    assert [line["replayed"] for line in lines] == [False, True]
    assert lines[1]["cost_usd"] == 0


def test_a_different_question_calls_the_api_again(client, fake):
    ask(client, QUESTION)
    ask(client, OTHER_QUESTION)
    assert len(fake.requests) == 2


def test_the_flag_turns_the_cache_off(client, fake, cache_files, monkeypatch):
    ask(client, QUESTION)  # The cache is on: this response is saved.
    monkeypatch.setenv("RESPONSE_CACHE", "off")
    ask(client, QUESTION)
    ask(client, OTHER_QUESTION)

    assert len(fake.requests) == 3, (
        "With RESPONSE_CACHE=off, each request must go to the API, also when a saved response exists."
    )
    assert len(cache_files()) == 1, "With the cache off, do not save responses."


# ---- step 6: the test questions ---------------------------------------------------


def test_there_are_30_questions_with_expected_dataset_ids(questions, catalogue):
    known = {dataset["id"] for dataset in catalogue}
    assert len(questions) == 30, f"evals/questions.jsonl has {len(questions)} questions, not 30."
    ids = [question["id"] for question in questions]
    assert len(set(ids)) == 30, "Each question needs its own id."
    texts = [question["question"].strip().lower() for question in questions]
    assert len(set(texts)) == 30, "Two questions have the same text."
    for question in questions:
        expected = question["expected_dataset_ids"]
        assert expected, f"{question['id']}: write at least one expected dataset id."
        unknown = sorted(set(expected) - known)
        assert not unknown, f"{question['id']}: these ids are not in the catalogue: {unknown}"


def test_5_questions_are_the_quick_set(questions):
    quick = [question["id"] for question in questions if question.get("quick")]
    assert len(quick) == 5, f"Mark 5 questions with \"quick\": true. Now {len(quick)} are marked."
