"""Week 3 checks: the typed answer, prompt caching and the test runner.

Run them with `make check WEEK=3`. They use the fake Claude API on localhost,
so they are free. Postgres must run (`make up`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from labkit.fake_claude import (
    error_reply,
    first_user_text,
    has_cache_control,
    json_reply,
    text_reply,
    tool_reply,
)
from labkit.sse import ask

REPO = Path(__file__).resolve().parents[3]
QUESTION = "Which datasets are about crude oil production?"
OTHER_QUESTION = "Which dataset has the length of roads?"
CRUDE_OIL = "saudi-crude-oil-production-from-sama-annual-statistics-2015-dec"
ANSWER = {
    "answer": "The dataset Crude Oil Production has the production of Saudi crude oil.",
    "dataset_ids": [CRUDE_OIL],
    "tools_called": ["search_datasets"],
}


# ---- step 2: the typed answer -------------------------------------------------------


def test_the_answer_model_has_the_three_fields():
    from assistant.schemas import Answer

    assert {"answer", "dataset_ids", "tools_called"} <= set(Answer.model_fields)
    answer = Answer.model_validate(ANSWER)
    assert answer.dataset_ids == [CRUDE_OIL]
    with pytest.raises(Exception):
        Answer.model_validate({"answer": "No ids."})


def test_the_request_asks_for_the_json_schema_of_the_answer(client, fake):
    ask(client, QUESTION)
    output_format = (fake.last_request.get("output_config") or {}).get("format") or {}

    assert output_format.get("type") == "json_schema", (
        "Send the schema of Answer in output_config.format, so the API returns valid JSON."
    )
    assert {"answer", "dataset_ids", "tools_called"} <= set(output_format["schema"]["properties"])


def test_the_stream_ends_with_a_validated_answer(client, fake, database):
    fake.script(tool_reply(("search_datasets", {"query": "crude oil production"})), json_reply(ANSWER))
    result = ask(client, QUESTION)

    assert result.answer is not None, "Send the validated Answer as one `answer` event."
    for field, value in ANSWER.items():
        assert result.answer[field] == value
    assert result.of("text") == [], (
        "Do not send the JSON text in pieces. Wait for the full answer, validate it, then send it."
    )
    assert [tool["name"] for tool in result.tools] == ["search_datasets"]
    assert result.names[-2:] == ["answer", "done"]
    assert result.errors == []


def test_a_cut_off_answer_gives_an_error_event(client, fake):
    fake.script(text_reply('{"answer": "The dataset Crude Oil Prod', stop_reason="max_tokens"))
    result = ask(client, QUESTION)

    assert result.status_code == 200
    assert result.answer is None, "A cut-off JSON document is not an answer."
    assert result.errors, "Send an `error` event with a message when the answer is not valid."
    assert result.done  # The stream still ends with `done`.


def test_an_answer_with_a_missing_field_gives_an_error_event(client, fake):
    fake.script(json_reply({"answer": "No ids."}))
    result = ask(client, QUESTION)

    assert result.answer is None, "Validate each answer with the Answer model."
    assert result.errors


# ---- step 3: prompt caching ---------------------------------------------------------


def test_cost_usd_counts_cache_writes_and_cache_reads():
    from anthropic.types import Usage

    from assistant.llm import cost_usd

    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
    )
    # input $0.10, output $0.50, cache write $0.125, cache read $0.01 for each million tokens
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(0.10 + 0.50 + 0.125 + 0.01)


def test_the_request_has_a_cache_breakpoint(client, fake):
    ask(client, QUESTION)
    assert has_cache_control(fake.last_request), (
        "Add cache_control to the request: on the last block of the part that does not change."
    )


def test_the_start_of_the_request_is_the_same_for_each_question(client, fake):
    ask(client, QUESTION)
    ask(client, OTHER_QUESTION)
    first, second = fake.requests

    assert json.dumps(first["tools"]) == json.dumps(second["tools"]), "The tools must not change."
    assert json.dumps(first["system"]) == json.dumps(second["system"]), (
        "The system prompt must be the same text in each request. A date, a request id or the "
        "question in the system prompt gives a new cache entry each time."
    )


def test_the_second_question_reads_the_prompt_cache(client, fake, request_log):
    ask(client, QUESTION)
    ask(client, OTHER_QUESTION)
    first, second = request_log()

    assert first["cache_creation_input_tokens"] > 0, (
        "The first request wrote nothing to the cache. Two possible causes: the tools and the "
        "system prompt together are below 512 tokens, or the request has no cache breakpoint."
    )
    assert second["cache_read_input_tokens"] > 0, (
        "The second question did not read the cache. Put the breakpoint on the last block that "
        "is the same in each request (the system prompt), and not on the question."
    )
    assert second["cost_usd"] < first["cost_usd"]


# ---- step 4: the test runner --------------------------------------------------------


def run_evals(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "evals.run", *args],
        cwd=REPO,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=300,
    )


def scripted_answers(questions, wrong_ids):
    """Reply to each question with its expected ids, or with a wrong id."""

    def reply(body):
        text = first_user_text(body)
        matches = [q for q in questions if q["question"] in text]
        if not matches:
            message = f"The request does not hold a question of evals/questions.jsonl: {text[:200]}"
            return error_reply(400, "invalid_request_error", message)
        question = max(matches, key=lambda q: len(q["question"]))
        ids = ["not-a-dataset"] if question["id"] in wrong_ids else question["expected_dataset_ids"]
        return json_reply({"answer": "Fake.", "dataset_ids": ids, "tools_called": []})

    return reply


def read_results(path: Path) -> list[dict]:
    assert path.exists(), f"The runner did not write the results to {path}."
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_the_runner_runs_the_quick_set_and_marks_pass_and_fail(fake, questions, tmp_path):
    quick = [q for q in questions if q.get("quick")]
    wrong = {quick[1]["id"], quick[3]["id"]}
    fake.always(scripted_answers(questions, wrong))
    out = tmp_path / "quick.jsonl"
    process = run_evals("--set", "quick", "--out", str(out))

    assert process.returncode == 0, process.stderr[-2000:]
    results = read_results(out)
    assert [r["id"] for r in results] == [q["id"] for q in quick]
    for result in results:
        assert result["passed"] is (result["id"] not in wrong), (
            f"{result['id']}: a question passes when the answer names each expected dataset id."
        )
        assert result["input_tokens"] > 0 and result["output_tokens"] > 0
        assert result["cost_usd"] > 0
        assert result["latency_ms"] > 0
    assert len(fake.requests) == 5


def test_the_runner_runs_all_30_questions(fake, questions, tmp_path):
    fake.always(scripted_answers(questions, set()))
    out = tmp_path / "all.jsonl"
    process = run_evals("--set", "all", "--out", str(out))

    assert process.returncode == 0, process.stderr[-2000:]
    results = read_results(out)
    assert len(results) == 30
    assert all(result["passed"] for result in results)


def test_the_runner_uses_the_response_cache_until_you_turn_it_off(fake, questions, tmp_path):
    fake.always(scripted_answers(questions, set()))
    assert run_evals("--set", "quick", "--out", str(tmp_path / "1.jsonl")).returncode == 0
    assert len(fake.requests) == 5

    assert run_evals("--set", "quick", "--out", str(tmp_path / "2.jsonl")).returncode == 0
    assert len(fake.requests) == 5, "The second run must replay the saved responses."
    assert all(result["cost_usd"] == 0 for result in read_results(tmp_path / "2.jsonl"))

    assert run_evals("--set", "quick", "--no-cache", "--out", str(tmp_path / "3.jsonl")).returncode == 0
    assert len(fake.requests) == 10, "With --no-cache, each question must go to the API."
