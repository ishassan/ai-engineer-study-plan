"""Week 14 checks: the agent as a LangGraph graph, on Claude and on OpenAI.

Run them with `make check WEEK=14`. They use the fake Claude API and the fake OpenAI API on
localhost, so they are free. Postgres and both model services must run (`make up`), and
Langfuse for the trace check. The checks use the graph (AGENT_IMPL=langgraph).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import test_week12
from phase4_helpers import (
    answer_value,
    ask,
    fake_of,
    prompt_text,
    returned_chunks,
    structured,
    tool_call,
    tool_calls,
    tool_results,
)
from test_week13 import PLAN_1, PLAN_2, QUESTION as TASK, Model

from assistant.config import PRICES_PER_MTOK

REPO = Path(__file__).resolve().parents[3]
PROVIDERS = ["anthropic", "openai"]
QUESTION = "Which datasets are about crude oil production?"
SEARCH = ("search_datasets", {"query": "crude oil production"})
BAD_ID = "no-such-dataset-for-the-check"
USAGE = [
    {"input_tokens": 1500, "output_tokens": 120, "cache_read_input_tokens": 1000},
    {"input_tokens": 2600, "output_tokens": 210},
]
RESULTS = REPO / "evals" / "results"
RUNS = [("handwritten", "anthropic"), ("langgraph", "anthropic"), ("langgraph", "openai")]


@pytest.fixture(autouse=True)
def graph(monkeypatch):
    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("AGENT_PLANNER", "off")
    monkeypatch.setenv("PROVIDER", "anthropic")


def model_name(provider: str) -> str:
    return "gpt-6-luna" if provider == "openai" else "claude-haiku-5-5"


def dataset_answer(provider: str, usage: dict[str, int] | None = None):
    """The answer names the first dataset that search_datasets returned."""

    def value(body: dict[str, Any]) -> dict[str, Any]:
        found = []
        for result in tool_results(body):
            try:
                data = json.loads(result["output"])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, list):
                found += [row["id"] for row in data if isinstance(row, dict) and "id" in row]
        return answer_value(body, "The catalogue has a dataset about crude oil production.", found[:1])

    return structured(provider, value, usage=usage)


def run(client, fake, fake_openai, monkeypatch, impl: str, provider: str):
    monkeypatch.setenv("AGENT_IMPL", impl)
    monkeypatch.setenv("PROVIDER", provider)
    fake.reset()
    fake_openai.reset()
    api = fake_of(provider, fake, fake_openai)
    api.script(tool_call(provider, SEARCH), dataset_answer(provider))
    return ask(client, QUESTION), api


# ---- step 2: the graph on two providers ------------------------------------------------------


def test_the_setting_chooses_the_graph(client, fake, fake_openai, monkeypatch, database):
    ask(client, QUESTION)
    assert fake.requests, "With AGENT_IMPL=langgraph and PROVIDER=anthropic, the request goes to Claude."
    agent = fake.headers[-1].get("user-agent", "")
    assert "langchain" in agent.lower(), f"The request must come from the LangChain model (User-Agent: {agent})."
    fake.reset()
    monkeypatch.setenv("PROVIDER", "openai")
    ask(client, QUESTION)
    assert fake_openai.requests and not fake.requests, "With PROVIDER=openai, the graph uses the OpenAI model."
    assert fake_openai.last_request["model"] == model_name("openai")


def test_the_same_question_gives_the_same_events(client, fake, fake_openai, monkeypatch, database):
    results = {(impl, provider): run(client, fake, fake_openai, monkeypatch, impl, provider)[0] for impl, provider in RUNS}

    def shape(result) -> dict[str, Any]:
        return {
            "events": [name for name in result.names if name != "text"],
            "tools": result.tools,
            "answer": result.answer,
            "done": sorted(result.done),
        }

    reference = shape(results[("handwritten", "anthropic")])
    assert reference["answer"] and reference["answer"]["dataset_ids"], "The hand-written loop gives no answer."
    for key, result in results.items():
        assert result.errors == [], f"{key}: {result.errors}"
        assert shape(result) == reference, f"{key} gives other events than the hand-written loop."


@pytest.mark.parametrize("provider", PROVIDERS)
def test_tool_results_go_back_with_their_ids(provider, client, fake, fake_openai, monkeypatch, database):
    monkeypatch.setenv("PROVIDER", provider)
    api = fake_of(provider, fake, fake_openai)
    api.script(tool_call(provider, SEARCH, ("get_dataset_schema", {"dataset_id": BAD_ID})), dataset_answer(provider))
    result = ask(client, QUESTION)

    assert result.answer is not None, result.errors
    assert len(api.requests) == 2, "Run both tools of the reply, then send one request with both results."
    second = api.requests[1]
    calls, outputs = tool_calls(second), tool_results(second)
    assert [call["name"] for call in calls] == ["search_datasets", "get_dataset_schema"]
    assert [output["id"] for output in outputs] == [call["id"] for call in calls], (
        "Each tool result must carry the ID of its tool call, in the format of the provider."
    )
    error = outputs[1]
    assert BAD_ID in error["output"], "The result of the failed call holds the error message."
    if provider == "anthropic":
        assert error["is_error"] is True, "Mark the result of a failed tool call as an error."
    assert [tool["is_error"] for tool in result.tools] == [False, True]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_done_event_has_the_tokens_and_the_cost(provider, client, fake, fake_openai, monkeypatch, database):
    monkeypatch.setenv("PROVIDER", provider)
    api = fake_of(provider, fake, fake_openai)
    api.script(tool_call(provider, SEARCH, usage=USAGE[0]), dataset_answer(provider, usage=USAGE[1]))
    done = ask(client, QUESTION).done

    price = PRICES_PER_MTOK[model_name(provider)]
    expected = (4100 * price["input"] + 330 * price["output"] + 1000 * price["cache_read"]) / 1_000_000
    assert (done["input_tokens"], done["output_tokens"], done["requests"]) == (4100, 330, 2), (
        "The `done` event gives the input tokens without the cache reads, as the Claude API does. "
        f"LangChain puts the cache reads into usage_metadata['input_tokens']. done: {done}"
    )
    assert done["cache_read_input_tokens"] == 1000, done
    assert done["model"] == model_name(provider)
    assert done["cost_usd"] == pytest.approx(expected, rel=1e-6), "Compute the cost from the usage of each reply."


# ---- step 3: plain code formats the citations ------------------------------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_plain_code_formats_the_citations_and_the_rule_of_week_7_holds(
    provider, client, fake, fake_openai, monkeypatch, services
):
    monkeypatch.setenv("PROVIDER", provider)
    api = fake_of(provider, fake, fake_openai)
    invented = "gastat-no-such-document-en:p1:c1"

    def cites(include_invented: bool):
        def value(body):
            chunk = returned_chunks(body)[0]
            citations = [{"document_title": "A title that the model got wrong", "page": 999, "chunk_id": chunk["chunk_id"]}]
            if include_invented:
                citations.append({"document_title": "No such document", "page": 1, "chunk_id": invented})
            return answer_value(body, "A road is a route for motor vehicles.", [], citations)

        return structured(provider, value)

    search = ("search_documents", {"query": "definition of a road in the land transport statistics"})
    api.script(tool_call(provider, search), cites(True), cites(False))
    result = ask(client, "How does the General Authority for Statistics define a road?")

    assert len(api.requests) == 3, (
        "The second reply cites a chunk ID that no search returned. Reject it and ask the model again, "
        "as the loop of week 7 does."
    )
    assert invented in prompt_text(api.requests[2]), "Tell the model which chunk IDs were wrong."
    chunk = returned_chunks(api.requests[1])[0]
    assert result.answer is not None, result.errors
    assert result.answer["citations"] == [
        {"document_title": chunk["title"], "page": chunk["page"], "chunk_id": chunk["chunk_id"]}
    ], "Plain code writes the title and the page of each citation from the result of search_documents."


# ---- the planner and the memory on the graph -------------------------------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_planner_runs_on_the_graph(provider, client, fake, fake_openai, monkeypatch, database):
    monkeypatch.setenv("PROVIDER", provider)
    monkeypatch.setenv("AGENT_PLANNER", "on")
    model = Model(provider)
    fake_of(provider, fake, fake_openai).always(model)
    result = ask(client, TASK)

    assert [plan["steps"] for plan in result.of("plan")] == [PLAN_1, PLAN_2], f"Requests: {model.kinds}"
    assert [tool["is_error"] for tool in result.tools] == [True, False]
    assert result.answer is not None and result.names[-2:] == ["answer", "done"]
    assert result.done["requests"] == len(model.kinds), "The `done` event counts the plan requests too."


MEMORY_CHECKS = [
    "test_a_conversation_keeps_its_history",
    "test_another_user_cannot_read_a_conversation",
    "test_a_long_conversation_is_compacted_and_continues",
    "test_a_fact_saved_in_one_conversation_reaches_the_next_one",
    "test_a_fact_does_not_reach_another_user",
]


@pytest.mark.parametrize("name", MEMORY_CHECKS)
def test_the_memory_of_week_12_works_on_the_graph(name, client, fake, sql, tables, embeddings, monkeypatch):
    """The checks of week 12 again, on the graph with Claude."""
    check = getattr(test_week12, name)
    arguments = {"client": client, "fake": fake, "sql": sql, "tables": tables, "embeddings": embeddings,
                 "monkeypatch": monkeypatch}
    check(**{key: arguments[key] for key in check.__code__.co_varnames[: check.__code__.co_argcount]})


# ---- tracing ---------------------------------------------------------------------------------


def test_the_trace_checks_of_week_8_pass_on_the_graph():
    """Run the checks of week 8 in a new process, on the graph with Claude."""
    env = dict(os.environ, AGENT_IMPL="langgraph", PROVIDER="anthropic", AGENT_PLANNER="off")
    for name in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        env.pop(name, None)  # The new process starts its own fake APIs.
    check = REPO / "phases" / "phase-3-evaluation" / "checks" / "test_week8.py"
    # The week 8 checks read each observation of the last seconds. Send the traces of the
    # earlier checks of this process first, and wait, so that they are not in that window.
    from langfuse import get_client

    get_client().flush()
    time.sleep(5)
    process = subprocess.run(
        [sys.executable, "-m", "pytest", str(check), "-q", "-p", "no:cacheprovider"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=600,
    )
    assert process.returncode == 0, (
        "The trace checks of week 8 fail on the graph. Pass the Langfuse CallbackHandler in the config "
        "of the run, keep @observe() on answer_events(), and keep your `tool` observations in the tool "
        f"node.\n{process.stdout[-3000:]}"
    )


# ---- step 4: the comparison ------------------------------------------------------------------


def load_run(impl: str, provider: str) -> dict[str, Any]:
    path = RESULTS / f"compare-{impl}-{provider}.json"
    assert path.exists(), f"{path.relative_to(REPO)} does not exist. Run `make compare IMPL={impl} PROVIDER={provider}`."
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_comparison_files_agree_with_the_test_set():
    from evals.run_testset import code_pass, load_cases

    cases = {case["id"]: case for case in load_cases()}
    ids = None
    for impl, provider in RUNS:
        data = load_run(impl, provider)
        assert (data["impl"], data["provider"]) == (impl, provider)
        rows = data["rows"]
        assert len(rows) >= 20, f"Run at least 20 cases of the test set for {impl} on {provider}."
        assert {row["id"] for row in rows} <= set(cases), "Each row is a case of evals/testset.jsonl."
        assert sum(bool(cases[row["id"]].get("expected_chunk_ids")) for row in rows) >= 5, (
            "Take at least 5 document cases (with expected chunk IDs)."
        )
        assert sum(bool(cases[row["id"]].get("expected_dataset_ids")) for row in rows) >= 5
        if ids is None:
            ids = sorted(row["id"] for row in rows)
        assert sorted(row["id"] for row in rows) == ids, "Run the same cases for each loop and provider."
        for row in rows:
            assert row["code_pass"] == code_pass(cases[row["id"]], row), f"{row['id']}: code_pass does not agree."
        score = sum(row["code_pass"] for row in rows) / len(rows)
        assert data["score"] == pytest.approx(score), "The score is the share of the cases with code_pass."


def test_the_graph_scores_at_least_as_well_as_the_handwritten_loop():
    handwritten = load_run("handwritten", "anthropic")["score"]
    graph = load_run("langgraph", "anthropic")["score"]
    openai = load_run("langgraph", "openai")["score"]
    print(f"\n  handwritten on Claude {handwritten:.2f}   graph on Claude {graph:.2f}   graph on OpenAI {openai:.2f}")
    assert graph >= handwritten, (
        f"The graph scores {graph:.2f} on Claude and the hand-written loop {handwritten:.2f}. Read the "
        "failing cases in the result files and fix the graph."
    )
