"""Reference solution."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "questions.jsonl"


def load_questions(which: str) -> list[dict]:
    rows = [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]
    return [row for row in rows if which == "all" or row.get("quick")]


def run_question(row: dict) -> dict:
    from assistant.agent import answer_events

    answer, done, errors = None, {}, []
    for event, data in answer_events(row["question"]):
        if event == "answer":
            answer = data
        elif event == "done":
            done = data
        elif event == "error":
            errors.append(data["message"])
    dataset_ids = answer["dataset_ids"] if answer else []
    return {
        "id": row["id"],
        "question": row["question"],
        "passed": answer is not None and set(row["expected_dataset_ids"]) <= set(dataset_ids),
        "expected_dataset_ids": row["expected_dataset_ids"],
        "dataset_ids": dataset_ids,
        "error": errors[0] if errors else None,
        "input_tokens": done.get("input_tokens", 0),
        "output_tokens": done.get("output_tokens", 0),
        "cache_read_input_tokens": done.get("cache_read_input_tokens", 0),
        "cost_usd": done.get("cost_usd", 0.0),
        "latency_ms": done.get("latency_ms", 0.0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["quick", "all"], default="quick")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.no_cache:
        os.environ["RESPONSE_CACHE"] = "off"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = args.out or ROOT / "evals" / "results" / f"{stamp}-{args.set}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with out.open("w") as file:
        for row in load_questions(args.set):
            result = run_question(row)
            results.append(result)
            file.write(json.dumps(result, ensure_ascii=False) + "\n")
            file.flush()
            mark = "PASS" if result["passed"] else "FAIL"
            print(
                f"{mark} {result['id']:5} {result['input_tokens']:>6} in {result['output_tokens']:>5} out "
                f"${result['cost_usd']:.5f} {result['latency_ms']:>8.0f} ms"
            )
    passed = sum(r["passed"] for r in results)
    cost = sum(r["cost_usd"] for r in results)
    print(f"passed {passed}/{len(results)}  cost ${cost:.4f}  results in {out}")


if __name__ == "__main__":
    main()
