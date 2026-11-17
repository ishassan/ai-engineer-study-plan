"""Helpers of the Phase 6 checks: the gateway configuration, the routes, and questions to the API."""

from __future__ import annotations

import csv
import json
import math
import uuid
from pathlib import Path
from typing import Any, Callable

from labkit import fake_claude, fake_openai
from labkit.gateway import UPSTREAM_KEYS
from labkit.sse import AskResult, parse_sse

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "gateway" / "config.yaml"
RESULTS = REPO / "evals" / "results"
TESTSET = REPO / "evals" / "testset.jsonl"

# The names of the routes that the checks use. The assistant sends them as its model names.
CLAUDE = "claude-haiku-5-5"
OPENAI = "gpt-6-luna"
OPEN = "qwen3-8b"
QUANTIZED = "qwen3-8b-awq"
FINE_TUNED = "qwen3-8b-arabic"
# The names of the models that vLLM serves (the default of vLLM is the name of the repository).
OPEN_UPSTREAM = "Qwen/Qwen3-8B"
QUANTIZED_UPSTREAM = "Qwen/Qwen3-8B-AWQ"


def gateway_config() -> dict[str, Any]:
    import yaml

    assert CONFIG.exists(), "gateway/config.yaml does not exist. Run `make start PHASE=6` first."
    return yaml.safe_load(CONFIG.read_text()) or {}


def new_user() -> str:
    return f"check-{uuid.uuid4().hex[:12]}"


def ask(client: Any, question: str, user: str = "analyst") -> AskResult:
    response = client.post("/ask", json={"question": question}, headers={"X-User": user})
    return AskResult(
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        events=parse_sse(response.text) if response.status_code == 200 else [],
    )


def events_text(result: AskResult) -> str:
    return json.dumps(result.events, ensure_ascii=False)[:1500]


def errors_of(result: AskResult) -> list[str]:
    return [str(data.get("message", "")) for data in result.errors]


def through_gateway_claude(fake: Any) -> bool:
    """True when each request of the fake Claude API came from the gateway (its provider key)."""
    return bool(fake.headers) and all(h.get("x-api-key") == UPSTREAM_KEYS["anthropic"] for h in fake.headers)


def openai_keys(fake: Any) -> set[str]:
    return {(h.get("authorization") or "").removeprefix("Bearer ") for h in fake.headers}


def claude_answer(text: str, **kwargs: Any) -> Callable[[dict[str, Any]], fake_claude.Reply]:
    return fake_claude.answer_reply(text, **kwargs)


def openai_answer(text: str, dataset_ids: list[str] | None = None,
                  usage: dict[str, int] | None = None) -> Callable[[dict[str, Any]], fake_openai.Reply]:
    """An answer of the fake OpenAI API (or vLLM) in the form that the request asks for."""

    def build(body: dict[str, Any]) -> fake_openai.Reply:
        if fake_openai.wants_json(body):
            value = {"answer": text, "dataset_ids": dataset_ids or [], "tools_called": [], "citations": []}
            return fake_openai.json_reply(value, usage=usage)
        return fake_openai.text_reply(text, usage=usage)

    return build


def dataset_cases(limit: int) -> list[dict[str, Any]]:
    """The first cases of evals/testset.jsonl that expect datasets and no passage."""
    assert TESTSET.exists(), "evals/testset.jsonl does not exist (Phase 3, week 9)."
    cases = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines() if line.strip()]
    chosen = [c for c in cases if c.get("expected_dataset_ids") and not c.get("expected_chunk_ids")]
    return chosen[:limit]


def answers_for(cases: list[dict[str, Any]]) -> Callable[[dict[str, Any]], fake_openai.Reply]:
    """Answer each question of these cases with its expected datasets, in the OpenAI format."""
    by_question = {case["question"]: case for case in cases}

    def build(body: dict[str, Any]) -> fake_openai.Reply:
        question = fake_openai.first_user_text(body)
        case = next((c for q, c in by_question.items() if q in question), None)
        ids = case["expected_dataset_ids"] if case else []
        return openai_answer(f"The datasets for this question are {', '.join(ids)}.", ids)(body)

    return build


def tool_then_answers(cases: list[dict[str, Any]]) -> Callable[[dict[str, Any]], fake_openai.Reply]:
    """Like answers_for(), but the model first calls search_datasets, as an agent does."""
    answer = answers_for(cases)

    def build(body: dict[str, Any]) -> fake_openai.Reply:
        if not fake_openai.tool_outputs(body):
            return fake_openai.tool_reply(("search_datasets", {"query": fake_openai.first_user_text(body)[:80]}))
        return answer(body)

    return build


# ---- the result files ---------------------------------------------------------------------------------

ROW_FIELDS = ("id", "question", "answer", "dataset_ids", "code_pass", "requests", "cost_usd", "latency_ms")
LOAD_FIELDS = ("concurrency", "requests", "ok", "errors", "seconds", "output_tokens", "tokens_per_second",
               "requests_per_hour", "latency_ms_p50", "latency_ms_p95")
LOADS = (1, 8, 32)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def all_case_ids() -> set[str]:
    return {case["id"] for case in read_jsonl(TESTSET)}


def model_rows(route: str) -> list[dict[str, Any]]:
    """The rows of the test set run of one route (make model-testset ROUTE=...)."""
    path = RESULTS / "models" / f"{route}.jsonl"
    assert path.exists(), (
        f"{path.relative_to(REPO)} does not exist. Run the test set on this model through the gateway: "
        f"make model-testset ROUTE={route}"
    )
    return read_jsonl(path)


def row_problems(route: str, rows: list[dict[str, Any]]) -> list[str]:
    problems = []
    missing = sorted(all_case_ids() - {row.get("id") for row in rows})
    if missing:
        problems.append(f"{route}: no row for {len(missing)} cases of the test set, for example {missing[:5]}")
    for row in rows:
        absent = [name for name in ROW_FIELDS if name not in row]
        if absent:
            problems.append(f"{route} {row.get('id')}: no field {absent}")
        elif not (isinstance(row["latency_ms"], (int, float)) and row["latency_ms"] > 0 and row["requests"] >= 1):
            problems.append(f"{route} {row['id']}: no model request was measured (requests {row['requests']}, "
                            f"latency_ms {row['latency_ms']})")
    return problems


def load_result(route: str) -> dict[str, Any]:
    """The result file of the load test of one route (make loadtest ROUTE=...)."""
    path = RESULTS / "load" / f"{route}.json"
    assert path.exists(), (
        f"{path.relative_to(REPO)} does not exist. Run the load test on the pod: make loadtest ROUTE={route} "
        "ARGS=\"--gpu A40 --gpu-price 0.59 --gpu-memory-gib <GiB>\""
    )
    return json.loads(path.read_text())


def close(a: float, b: float, tolerance: float = 0.02) -> bool:
    return abs(a - b) <= tolerance * max(abs(a), abs(b), 1e-9)


def load_problems(route: str, result: dict[str, Any]) -> list[str]:
    problems = []
    if result.get("model") != route:
        problems.append(f"model is {result.get('model')!r}, not {route!r}")
    for name in ("gpu_price_per_hour", "gpu_memory_gib"):
        value = result.get(name)
        if not (isinstance(value, (int, float)) and value > 0):
            problems.append(f"{name} is {value!r}: give it with --gpu-price and --gpu-memory-gib")
    if not result.get("gpu"):
        problems.append("gpu is empty: give it with --gpu")
    loads = {load.get("concurrency"): load for load in result.get("loads") or []}
    for concurrency in LOADS:
        load = loads.get(concurrency)
        if load is None:
            problems.append(f"no result for the load {concurrency}")
            continue
        absent = [name for name in LOAD_FIELDS if name not in load]
        if absent:
            problems.append(f"load {concurrency}: no field {absent}")
            continue
        if load["ok"] < 1 or load["ok"] + load["errors"] != load["requests"]:
            problems.append(f"load {concurrency}: ok {load['ok']} and errors {load['errors']} do not add up to "
                            f"requests {load['requests']}, or no request succeeded")
        elif load["seconds"] <= 0 or not close(load["tokens_per_second"], load["output_tokens"] / load["seconds"]):
            problems.append(f"load {concurrency}: tokens_per_second is not output_tokens / seconds")
        elif not close(load["requests_per_hour"], load["ok"] / load["seconds"] * 3600):
            problems.append(f"load {concurrency}: requests_per_hour is not ok / seconds * 3600")
        elif not 0 < load["latency_ms_p50"] <= load["latency_ms_p95"]:
            problems.append(f"load {concurrency}: the latencies are not 0 < p50 <= p95")
    return problems


# ---- the comparison table ---------------------------------------------------------------------------

TABLE = RESULTS / "model_comparison.csv"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(fraction * len(ordered))) - 1]


def comparison_table() -> dict[str, dict[str, str]]:
    assert TABLE.exists(), (
        "evals/results/model_comparison.csv does not exist. Run all cells of "
        "phases/phase-6-open-models/notebooks/model_comparison.ipynb (step 5)."
    )
    with TABLE.open(newline="") as file:
        return {row["model"]: row for row in csv.DictReader(file)}


def table_problems(routes: list[str]) -> list[str]:
    """Compare each row of the table with its result file: the table must hold your newest results."""
    table, problems = comparison_table(), []
    for route in routes:
        row = table.get(route)
        if row is None:
            problems.append(f"no row for {route}: run the notebook again after the new result file")
            continue
        rows = model_rows(route)
        quality = round(sum(bool(r["code_pass"]) for r in rows) / len(rows), 3)
        latencies = [r["latency_ms"] for r in rows]
        expected = {"cases": len(rows), "quality": quality, "latency_ms_p50": round(percentile(latencies, 0.5), 1),
                    "latency_ms_p95": round(percentile(latencies, 0.95), 1)}
        for name, value in expected.items():
            try:
                found = float(row.get(name) or "nan")
            except ValueError:
                found = float("nan")
            if not abs(found - value) <= 1e-6 + 1e-3 * abs(value):
                problems.append(f"{route}: {name} is {row.get(name)!r} in the table, but {value} in the result "
                                "file. Run the notebook again.")
    return problems
