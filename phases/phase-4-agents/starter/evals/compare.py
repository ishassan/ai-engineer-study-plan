"""Run the test set on one loop and one provider, and write one result file. Week 14.

This file is complete.

    make compare IMPL=handwritten PROVIDER=anthropic
    make compare IMPL=langgraph PROVIDER=anthropic
    make compare IMPL=langgraph PROVIDER=openai
    make compare IMPL=langgraph PROVIDER=openai ARGS="--limit 30"   the first 30 cases
    make compare ... ARGS="--ids t001,t031"                          some cases

The hand-written loop uses Claude only. Each case runs through the loop that IMPL names,
with the model that PROVIDER names, as one Langfuse trace (tags `compare` and
`<impl>-<provider>`). The result file is evals/results/compare-<impl>-<provider>.json:

    impl, provider, created, score, cost_usd, rows

Each row has the fields of a row of `make testset` (week 9), with `code_pass`: the answer
names each expected dataset ID, and cites an expected chunk when the case has some. The
score is the share of the cases with code_pass. Run the same cases for each loop and
provider, so the scores compare.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from langfuse import get_client, propagate_attributes

from evals.run_testset import TESTSET, cited_passages, code_pass, load_cases

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evals" / "results"


def run_case(case: dict, run_name: str) -> dict:
    """Run one case through the loop of AGENT_IMPL and return its row."""
    from assistant.api import agent

    langfuse = get_client()
    answer, done, errors, tools = None, {}, [], []
    with langfuse.start_as_current_observation(
        as_type="span", name="compare-case", input={"case_id": case["id"], "question": case["question"]}
    ) as span:
        with propagate_attributes(trace_name="compare-case", tags=["compare", run_name], metadata={"case_id": case["id"]}):
            trace_id = langfuse.get_current_trace_id()
            for event, data in agent()(case["question"]):
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
        "model": done.get("model"),
        "requests": done.get("requests", 0),
        "input_tokens": done.get("input_tokens", 0),
        "output_tokens": done.get("output_tokens", 0),
        "cost_usd": done.get("cost_usd", 0.0),
        "latency_ms": done.get("latency_ms", 0.0),
    }
    row["code_pass"] = code_pass(case, row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--impl", choices=["handwritten", "langgraph"], required=True)
    parser.add_argument("--provider", choices=["anthropic", "openai"], required=True)
    parser.add_argument("--testset", type=Path, default=TESTSET)
    parser.add_argument("--ids", help="Comma-separated case IDs. Default: all cases.")
    parser.add_argument("--limit", type=int, help="Run only the first N cases.")
    parser.add_argument("--no-cache", action="store_true", help="Turn the response cache of the hand-written loop off.")
    args = parser.parse_args()
    if args.impl == "handwritten" and args.provider != "anthropic":
        parser.error("The hand-written loop uses Claude only. Use --provider anthropic.")
    os.environ.update(AGENT_IMPL=args.impl, PROVIDER=args.provider, AGENT_PLANNER="off")
    if args.no_cache:
        os.environ["RESPONSE_CACHE"] = "off"

    cases = load_cases(args.testset)
    if args.ids:
        wanted = set(args.ids.split(","))
        cases = [case for case in cases if case["id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    run_name = f"{args.impl}-{args.provider}"
    rows = []
    for case in cases:
        row = run_case(case, run_name)
        rows.append(row)
        mark = "PASS" if row["code_pass"] else "FAIL"
        print(f"{mark} {row['id']:6} {row['requests']} requests  ${row['cost_usd']:.5f}  {row['trace_id']}", flush=True)
    get_client().flush()
    score = sum(row["code_pass"] for row in rows) / len(rows) if rows else 0.0
    result = {
        "impl": args.impl,
        "provider": args.provider,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "score": score,
        "cost_usd": sum(row["cost_usd"] for row in rows),
        "rows": rows,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"compare-{run_name}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"score {score:.2f} over {len(rows)} cases  cost ${result['cost_usd']:.4f}  results in {out}")


if __name__ == "__main__":
    main()
