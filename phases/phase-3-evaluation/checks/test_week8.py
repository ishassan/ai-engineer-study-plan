"""Week 8 checks: one /ask request is one trace in Langfuse, with each step inside it.

Run them with `make check WEEK=8`. Langfuse, Postgres and both model services must run
(`make up`). The model is the fake Claude API of the lab, so the checks are free. The checks
send one question that calls three tools, and read the trace back through the public API of
Langfuse.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from labkit.fake_claude import json_reply, tool_reply
from labkit.sse import ask

REPO = Path(__file__).resolve().parents[3]
MODEL = "claude-haiku-5-5"
TOOL_CALLS = [
    ("search_datasets", {"query": "crude oil production"}),
    ("get_dataset_schema", {"dataset_id": "no-such-dataset-for-the-check"}),
    ("search_documents", {"query": "definition of a road in the land transport statistics"}),
]
USAGE = [{"input_tokens": 1500, "output_tokens": 120}, {"input_tokens": 2600, "output_tokens": 210}]


def returned_chunk_ids(body: dict[str, Any]) -> list[str]:
    """The chunk IDs in the results of search_documents in the messages of a request."""
    ids = []
    for message in body["messages"]:
        content = message.get("content")
        for block in [] if isinstance(content, str) else content:
            if block.get("type") != "tool_result" or block.get("is_error"):
                continue
            text = block["content"] if isinstance(block["content"], str) else block["content"][0]["text"]
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                data = next((value for value in data.values() if isinstance(value, list)), [])
            if isinstance(data, list):
                ids += [item["chunk_id"] for item in data if isinstance(item, dict) and "chunk_id" in item]
    return ids


def final_answer(body: dict[str, Any]):
    chunk_ids = returned_chunk_ids(body)
    citations = [{"document_title": "A report", "page": 1, "chunk_id": chunk_id} for chunk_id in chunk_ids[:1]]
    # The title and page of a citation are not checked by the loop of week 7, only the chunk ID.
    return json_reply(
        {"answer": "Two datasets, and a definition.", "dataset_ids": [], "tools_called": [], "citations": citations},
        usage=USAGE[1],
    )


@pytest.fixture(scope="module")
def traced(langfuse, services) -> dict[str, Any]:
    """Send one question through /ask, and read its observations back from Langfuse."""
    from labkit.plugin import _state, make_client

    fake = _state["fake"]
    fake.reset()
    from assistant.api import app

    token = uuid.uuid4().hex[:12]
    question = f"Which datasets are about crude oil, and how is a road defined? (check {token})"
    fake.script(tool_reply(*TOOL_CALLS, usage=USAGE[0]), final_answer)
    since = datetime.now(timezone.utc) - timedelta(seconds=2)
    result = ask(make_client(app), question)
    requests = list(fake.requests)

    def ready(observations: list[dict[str, Any]]) -> bool:
        kinds = [o["type"] for o in observations]
        return kinds.count("GENERATION") >= len(requests) and kinds.count("TOOL") >= len(TOOL_CALLS)

    observations = langfuse.wait_for(since, ready, timeout=30)
    roots = [o for o in observations if token in (o.get("input") or "")]
    return {
        "result": result,
        "requests": requests,
        "observations": observations,
        "token": token,
        "trace_ids": {o["traceId"] for o in observations},
        "trace_id": roots[0]["traceId"] if roots else None,
    }


def of_trace(traced: dict[str, Any], kind: str | None = None) -> list[dict[str, Any]]:
    assert traced["trace_id"], (
        "No observation in Langfuse holds the question of the request. Trace each /ask request: "
        "the root observation of the trace has the question as its input."
    )
    found = [o for o in traced["observations"] if o["traceId"] == traced["trace_id"]]
    found = [o for o in found if kind is None or o["type"] == kind]
    return sorted(found, key=lambda o: o["startTime"])


def test_langfuse_runs_and_accepts_the_keys(langfuse):
    projects = langfuse.get("/api/public/projects")["data"]
    assert projects, "The keys of .env belong to no project."


def test_the_request_works(traced):
    result = traced["result"]
    assert result.status_code == 200
    assert [tool["name"] for tool in result.tools] == [name for name, _ in TOOL_CALLS]
    assert result.answer is not None, f"The stream has no answer. Errors: {result.errors}"
    assert len(traced["requests"]) == 2


def test_one_request_is_one_trace(traced):
    of_trace(traced)
    others = traced["trace_ids"] - {traced["trace_id"]}
    assert not others, (
        f"The request made {len(traced['trace_ids'])} traces, and not one. A step that starts "
        "after a `yield` of answer_events() lost the current span. Starlette runs each step of a "
        "streaming response in a worker thread with a copy of the context, so a `with` block "
        "around the loop does not stay current. Use the @observe() decorator on answer_events(): "
        "it runs each step of the generator in the context of the trace."
    )
    roots = [o for o in of_trace(traced) if not o["parentObservationId"]]
    assert len(roots) == 1, f"The trace must have one root observation, not {len(roots)}."
    assert traced["token"] in (roots[0].get("input") or ""), "The input of the root observation is the question."


def test_each_step_is_inside_the_root_observation(traced):
    observations = of_trace(traced)
    by_id = {o["id"]: o for o in observations}
    root = next(o for o in observations if not o["parentObservationId"])
    for observation in observations:
        assert observation.get("endTime"), f"The observation {observation['name']} has no end time. End each span."
        assert observation["startTime"] >= root["startTime"] and observation["endTime"] <= root["endTime"], (
            f"The observation {observation['name']} is outside the time of the root observation."
        )
        parent = observation["parentObservationId"]
        while parent:
            assert parent in by_id, f"The parent of {observation['name']} is not in the trace."
            parent = by_id[parent]["parentObservationId"]


def test_each_model_call_is_one_generation_with_model_and_tokens(traced):
    generations = of_trace(traced, "GENERATION")
    assert len(generations) == len(traced["requests"]), (
        f"The request sent {len(traced['requests'])} requests to Claude, and the trace has "
        f"{len(generations)} generations. Make one generation for each model call. Note: the "
        "anthropic SDK makes its own span for each API call when a tracer is registered. Keep "
        "that span or your own, not both: Langfuse would count the cost of the call twice."
    )
    for generation, usage in zip(generations, USAGE):
        assert generation.get("model") == MODEL, f"Set the model on the generation: {generation.get('model')!r}"
        assert generation.get("inputUsage") == usage["input_tokens"], (
            f"The generation has {generation.get('inputUsage')} input tokens, and the API returned "
            f"{usage['input_tokens']}. Send usage_details with the tokens of the response."
        )
        assert generation.get("outputUsage") == usage["output_tokens"]


def test_each_generation_has_its_cost(traced):
    generations = of_trace(traced, "GENERATION")
    assert generations, "The trace has no generation."
    costs = [generation.get("totalCost") for generation in generations]
    assert all(cost and cost > 0 for cost in costs), f"Each generation needs its cost: {costs}"
    expected = traced["result"].done["cost_usd"]
    assert sum(costs) == pytest.approx(expected, rel=0.01, abs=1e-9), (
        f"The costs of the generations add up to {sum(costs):.6f} dollars, and the `done` event says "
        f"{expected:.6f}. Send the cost of your cost_usd() in cost_details."
    )


def test_each_tool_call_is_one_tool_observation(traced):
    tools = of_trace(traced, "TOOL")
    assert sorted(o["name"] for o in tools) == sorted(name for name, _ in TOOL_CALLS), (
        "Make one observation of the type `tool` for each tool call, with the name of the tool. "
        f"The trace has: {[o['name'] for o in tools]}"
    )
    for name, tool_input in TOOL_CALLS:
        observation = next(o for o in tools if o["name"] == name)
        value = next(iter(tool_input.values()))
        assert value in (observation.get("input") or ""), f"The input of the tool {name} is not on its observation."


def test_a_failed_tool_call_has_the_level_error(traced):
    tools = {o["name"]: o for o in of_trace(traced, "TOOL")}
    failed = tools.get("get_dataset_schema")
    assert failed is not None, "The trace has no observation of the tool get_dataset_schema."
    assert failed.get("level") == "ERROR", (
        "The call of get_dataset_schema with an unknown ID raised an error. Give its observation "
        "the level ERROR and the message of the error, so you can filter failed steps in Langfuse."
    )
    others = [o for o in tools.values() if o["name"] != "get_dataset_schema"]
    assert all(o.get("level") != "ERROR" for o in others), "Only the failed tool call has the level ERROR."


def test_the_retrieval_is_a_step_inside_the_document_search(traced):
    observations = of_trace(traced)
    by_id = {o["id"]: o for o in observations}
    search = next((o for o in observations if o["type"] == "TOOL" and o["name"] == "search_documents"), None)
    assert search is not None, "The trace has no observation of the tool search_documents."
    retrievals = [o for o in observations if o["type"] == "RETRIEVER"]
    assert retrievals, "Make an observation of the type `retriever` for the retrieval step in retrieve()."

    def inside_search(observation: dict[str, Any]) -> bool:
        parent = observation["parentObservationId"]
        while parent:
            if parent == search["id"]:
                return True
            parent = by_id.get(parent, {}).get("parentObservationId")
        return False

    inside = [o for o in retrievals if inside_search(o)]
    assert inside, "The retrieval step must be inside the observation of the tool search_documents."
    returned = returned_chunk_ids(traced["requests"][-1])
    assert returned, "The tool search_documents returned no chunk."
    output = " ".join(o.get("output") or "" for o in inside)
    missing = [chunk_id for chunk_id in returned if chunk_id not in output]
    assert not missing, f"The output of the retrieval step must name the chunks that it found. Missing: {missing}"


@pytest.mark.parametrize(
    "case, change",
    [
        ("Langfuse is down", {"LANGFUSE_BASE_URL": "http://127.0.0.1:9"}),
        ("no Langfuse keys", {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}),
    ],
)
def test_the_service_answers_without_langfuse(case, change, fake):
    code = (
        "import json\n"
        "from assistant.agent import answer_events\n"
        "print(json.dumps([event for event, _ in answer_events('What is a dataset?')]))\n"
    )
    env = dict(os.environ, **change)
    started = time.monotonic()
    process = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=120
    )
    seconds = time.monotonic() - started
    assert process.returncode == 0, f"With {case}, answer_events() failed:\n{process.stderr[-2000:]}"
    events = json.loads(process.stdout.strip().splitlines()[-1])
    assert events[-1] == "done" and "answer" in events, f"With {case}, the events are {events}."
    assert seconds < 30, f"With {case}, one question took {seconds:.0f} s. Tracing must not hold up the answer."
