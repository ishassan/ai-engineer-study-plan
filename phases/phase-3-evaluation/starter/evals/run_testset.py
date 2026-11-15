"""Run the test set through the assistant, with one Langfuse trace for each case. Week 9.

This file is complete.

    make testset                             all cases of evals/testset.jsonl
    make testset ARGS="--ids t001,t031"      some cases
    make testset ARGS="--limit 10"           the first 10 cases
    make testset ARGS="--no-cache"           send each request to the API

Each case runs answer_events() inside an observation "testset-case". So the trace of a case
holds your trace of the request, and this script knows its trace ID. The traces of one run
have the tag `run:<name of the run>`, so you can filter them in the Langfuse UI.

The result file is evals/results/testset-<time>.jsonl, one JSON line for each case:

    id, language, question, expected_dataset_ids, expected_chunk_ids,
    trace_id, answer, dataset_ids, citations, cited_passages, tools, errors,
    code_pass, requests, cost_usd, latency_ms

`code_pass` is a first automatic check, not the result of your error analysis: the answer
names each expected dataset ID, and, when the case has expected chunk IDs, it cites at least
one of them. `cited_passages` holds the text of each cited chunk, read from Postgres.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langfuse import get_client, propagate_attributes

ROOT = Path(__file__).resolve().parent.parent
TESTSET = ROOT / "evals" / "testset.jsonl"


def load_cases(path: Path = TESTSET) -> list[dict[str, Any]]:
    """The cases of the test set, in the order of the file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def cited_passages(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The stored text of each cited chunk."""
    from assistant.db import query

    ids = [citation.get("chunk_id") for citation in citations if citation.get("chunk_id")]
    if not ids:
        return []
    rows = query("SELECT id, page, text FROM chunks WHERE id = ANY(%s)", (ids,))
    by_id = {row["id"]: row for row in rows}
    return [
        {"chunk_id": chunk_id, "page": by_id[chunk_id]["page"], "text": by_id[chunk_id]["text"]}
        for chunk_id in ids
        if chunk_id in by_id
    ]


def code_pass(case: dict[str, Any], row: dict[str, Any]) -> bool:
    if row["answer"] is None:
        return False
    if not set(case.get("expected_dataset_ids") or []) <= set(row["dataset_ids"]):
        return False
    expected_chunks = set(case.get("expected_chunk_ids") or [])
    cited = {citation.get("chunk_id") for citation in row["citations"]}
    return not expected_chunks or bool(expected_chunks & cited)


def run_case(case: dict[str, Any], run_name: str = "manual") -> dict[str, Any]:
    """Run one case through answer_events() and return the row of the result file."""
    from assistant.agent import answer_events

    langfuse = get_client()
    answer, done, errors, tools = None, {}, [], []
    with langfuse.start_as_current_observation(
        as_type="span", name="testset-case", input={"case_id": case["id"], "question": case["question"]}
    ) as span:
        with propagate_attributes(
            trace_name="testset-case",
            tags=["testset", f"run:{run_name}"],
            metadata={"case_id": case["id"], "run": run_name},
        ):
            trace_id = langfuse.get_current_trace_id()
            for event, data in answer_events(case["question"]):
                if event == "answer":
                    answer = data
                elif event == "done":
                    done = data
                elif event == "error":
                    errors.append(data.get("message", ""))
                elif event == "tool":
                    tools.append(data)
        span.update(output=answer or {"errors": errors})
    citations = (answer or {}).get("citations", [])
    row = {
        "id": case["id"],
        "language": case.get("language"),
        "question": case["question"],
        "expected_dataset_ids": case.get("expected_dataset_ids", []),
        "expected_chunk_ids": case.get("expected_chunk_ids", []),
        "trace_id": trace_id,
        "answer": (answer or {}).get("answer"),
        "dataset_ids": (answer or {}).get("dataset_ids", []),
        "citations": citations,
        "cited_passages": cited_passages(citations),
        "tools": tools,
        "errors": errors,
        "requests": done.get("requests", 0),
        "cost_usd": done.get("cost_usd", 0.0),
        "latency_ms": done.get("latency_ms", 0.0),
    }
    row["code_pass"] = code_pass(case, row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--testset", type=Path, default=TESTSET)
    parser.add_argument("--ids", help="Comma-separated case IDs. Default: all cases.")
    parser.add_argument("--limit", type=int, help="Run only the first N cases.")
    parser.add_argument("--no-cache", action="store_true", help="Turn the response cache off.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.no_cache:
        os.environ["RESPONSE_CACHE"] = "off"

    cases = load_cases(args.testset)
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [case for case in cases if case["id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = args.out or ROOT / "evals" / "results" / f"testset-{stamp}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    with out.open("w", encoding="utf-8") as file:
        for case in cases:
            row = run_case(case, run_name=stamp)
            rows.append(row)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            mark = "PASS" if row["code_pass"] else "FAIL"
            print(f"{mark} {row['id']:6} {row['requests']} requests  ${row['cost_usd']:.5f}  {row['trace_id']}")
    get_client().flush()
    passed = sum(row["code_pass"] for row in rows)
    cost = sum(row["cost_usd"] for row in rows)
    print(f"code_pass {passed}/{len(rows)}  cost ${cost:.4f}  results in {out}")


if __name__ == "__main__":
    main()
