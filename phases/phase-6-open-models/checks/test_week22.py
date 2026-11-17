"""Week 22: an open model on vLLM.

The checks need no GPU: the fake OpenAI API stands in for vLLM behind the gateway. vLLM speaks
the same protocol (the OpenAI Chat Completions API), so a route that works here works with the
pod when its address and key are right.

Fixed names:
- the route `qwen3-8b`, which vLLM serves as `Qwen/Qwen3-8B`
- scripts/loadtest.py and its result file evals/results/load/qwen3-8b.json
- the test set results evals/results/models/<route>.jsonl (make model-testset)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from labkit import fake_openai as openai_api
from labkit.gateway import UPSTREAM_KEYS
from phase6_helpers import (
    CLAUDE,
    OPEN,
    OPEN_UPSTREAM,
    REPO,
    ask,
    dataset_cases,
    events_text,
    load_problems,
    load_result,
    model_rows,
    openai_keys,
    row_problems,
    tool_then_answers,
)

QUESTION = "Which datasets show the electricity consumption by sector?"
DELAY = 0.4
OUTPUT_TOKENS = 120


def route_names(gateway) -> set[str]:
    status, body = gateway.admin("GET", "/model/info")
    assert status == 200, f"GET /model/info of the gateway answered {status}: {body}"
    return {row.get("model_name") for row in body.get("data", [])}


# ---- step 3: the open model in the gateway ------------------------------------------------------


def test_the_gateway_has_a_route_for_the_open_model(gateway):
    assert OPEN in route_names(gateway), (
        f"The gateway has no route `{OPEN}`. Add it to model_list: the model `hosted_vllm/{OPEN_UPSTREAM}`, "
        "with api_base and api_key from VLLM_API_BASE and VLLM_API_KEY (step 3)."
    )


def test_the_assistant_answers_with_the_open_model_through_the_gateway(client, fake_openai, gateway, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", OPEN)
    cases = dataset_cases(1)
    fake_openai.always(tool_then_answers(cases))
    result = ask(client, cases[0]["question"])
    assert result.answer is not None, (
        f"The hand-written loop got no answer from `{OPEN}` through the gateway. A model without a token "
        f"price must not stop the loop (cost_usd of llm.py). Events: {events_text(result)}"
    )
    models = {body.get("model") for body in fake_openai.requests}
    assert models == {OPEN_UPSTREAM}, f"vLLM must get the model `{OPEN_UPSTREAM}`, not {models}."
    assert openai_keys(fake_openai) == {UPSTREAM_KEYS["vllm"]}, (
        "The route must send the key of vLLM (api_key: os.environ/VLLM_API_KEY). vLLM refuses a request "
        "without the key of its --api-key flag."
    )
    assert len(fake_openai.requests) >= 2 and openai_api.tool_outputs(fake_openai.requests[-1]), (
        "The tool call of the open model did not come back to the loop with its result."
    )
    assert result.done.get("cost_usd") == 0, f"An open model has no token price: cost_usd must be 0, not {result.done}."


def test_the_test_set_runs_on_the_open_model_through_the_gateway(fake_openai, gateway, monkeypatch):
    from evals.run_testset import run_case

    monkeypatch.setenv("CLAUDE_MODEL", OPEN)
    cases = dataset_cases(3)
    fake_openai.always(tool_then_answers(cases))
    rows = [run_case(case, run_name="check-week22") for case in cases]
    failed = [(row["id"], row["errors"]) for row in rows if not row["code_pass"]]
    assert not failed, f"These cases did not pass on the open model through the gateway: {failed}"


# ---- step 3: the load test ------------------------------------------------------------------------

_LOAD_RUN: dict[str, object] = {}


def run_loadtest(fake_openai, tmp_path: Path) -> tuple[subprocess.CompletedProcess, dict | None, int]:
    """Run scripts/loadtest.py once for the loads 1 and 8, against the fake vLLM with a delay."""
    if not _LOAD_RUN:
        fake_openai.delay = DELAY
        fake_openai.always(openai_api.text_reply("Three datasets.", usage={"input_tokens": 40, "output_tokens": OUTPUT_TOKENS}))
        out = tmp_path / "load.json"
        command = [sys.executable, "scripts/loadtest.py", "--model", OPEN, "--loads", "1,8", "--requests-per-slot", "2",
                   "--gpu", "check", "--gpu-price", "1.0", "--gpu-memory-gib", "1.0", "--out", str(out)]
        process = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=300, env=dict(os.environ))
        result = json.loads(out.read_text()) if out.exists() else None
        _LOAD_RUN.update(process=process, result=result, in_flight=fake_openai.max_in_flight,
                         requests=list(fake_openai.requests))
    return _LOAD_RUN["process"], _LOAD_RUN["result"], _LOAD_RUN["in_flight"]  # type: ignore[return-value]


def loads_of(fake_openai, tmp_path) -> dict[int, dict]:
    process, result, _ = run_loadtest(fake_openai, tmp_path)
    assert process.returncode == 0 and result is not None, (
        f"scripts/loadtest.py failed (exit {process.returncode}):\n{(process.stdout + process.stderr)[-3000:]}"
    )
    return {load["concurrency"]: load for load in result["loads"]}


def test_the_load_test_sends_each_load_at_the_same_time(fake_openai, gateway, tmp_path):
    loads = loads_of(fake_openai, tmp_path)
    _, _, in_flight = run_loadtest(fake_openai, tmp_path)
    assert set(loads) == {1, 8}, f"The result file must have one item for each load: {sorted(loads)}"
    assert in_flight == 8, (
        f"At the load 8, vLLM had at most {in_flight} requests at the same time, not 8. Send the requests of a "
        "load at the same time (asyncio.gather, with a semaphore of the size of the load)."
    )
    assert loads[1]["seconds"] >= 2 * DELAY * 0.95, (
        f"At the load 1 the 2 requests must go one after the other, but they took {loads[1]['seconds']} s."
    )
    requests = _LOAD_RUN["requests"]
    assert {body.get("model") for body in requests} == {OPEN_UPSTREAM}, "The load test must call the route through the gateway."  # type: ignore[union-attr]


def test_the_load_test_measures_tokens_per_second_and_latency(fake_openai, gateway, tmp_path):
    loads = loads_of(fake_openai, tmp_path)
    for concurrency, load in loads.items():
        expected = 2 * concurrency
        assert load["requests"] == expected and load["ok"] == expected and load["errors"] == 0, (
            f"Load {concurrency}: {load['ok']} of {load['requests']} requests succeeded, not {expected} of {expected}."
        )
        assert load["output_tokens"] == OUTPUT_TOKENS * expected, (
            f"Load {concurrency}: output_tokens is {load['output_tokens']}, not the sum of the usage of the answers "
            f"({OUTPUT_TOKENS * expected})."
        )
        assert load["latency_ms_p50"] >= DELAY * 1000, (
            f"Load {concurrency}: the latency p50 is {load['latency_ms_p50']} ms, but each answer took at least "
            f"{DELAY * 1000:.0f} ms. Measure from the start of the request to the end of the answer."
        )
    problems = [p for p in load_problems(OPEN, _LOAD_RUN["result"]) if "load 32" not in p]  # type: ignore[arg-type]
    assert not problems, f"The result of the load test is not right: {problems}"


# ---- step 3: the result files -----------------------------------------------------------------------


@pytest.mark.parametrize("route", [CLAUDE, OPEN])
def test_the_test_set_results_of_the_hosted_and_the_open_model(route):
    problems = row_problems(route, model_rows(route))
    assert not problems, f"The test set results are not complete: {problems[:10]}"


def test_the_load_test_result_of_the_open_model():
    problems = load_problems(OPEN, load_result(OPEN))
    assert not problems, f"evals/results/load/{OPEN}.json is not right: {problems}"
