"""Score the agent on multi-step tasks: the final result and the path. Week 17.

    make agent-eval                                   all tasks of evals/agent_tasks.jsonl
    make agent-eval ARGS="--ids a01,a02"              some tasks
    make agent-eval ARGS="--min-result 0.8 --min-path 0.8"   exit 1 below these scores (CI)

Each task runs through the graph (assistant/graph.py) as one Langfuse trace (tag
`agent-eval`). The runner refuses each approval: a task never registers a dataset. The
result file is evals/results/agent-tasks.json:

    created, result_score, path_score, cost_usd, rows

Each row has the task ID, the answer, the tool calls of the agent (`calls`, each with `name`
and `args`), and the two scores of the task. The scores of the file are the mean scores of
the rows.

The runner is complete. Your work: result_score() and path_score().

A line of evals/agent_tasks.jsonl:

    {"id": "a01",
     "task": "How many records does ... have, and who publishes it?",
     "expected_result": {"dataset_ids": ["cement-production-and-sales"], "contains": ["112"]},
     "expected_tools": [{"name": "search_datasets"},
                        {"name": "get_dataset_stats", "args": {"dataset_id": "cement-production-and-sales"}}]}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langfuse import get_client, propagate_attributes

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "evals" / "agent_tasks.jsonl"
RESULTS = ROOT / "evals" / "results"
USER = "agent-eval"


def result_score(expected: dict[str, Any], answer: dict[str, Any] | None) -> float:
    """The score of the final result of one task, from 0.0 to 1.0.

    `expected` is the `expected_result` of the task: `dataset_ids` (each one must be in the
    dataset_ids of the answer) and `contains` (each text must be in the answer text). `answer`
    is the `answer` event of the agent, or None when the agent gave no answer (score 0.0).
    A result that meets each expectation scores 1.0. Choose how strictly you compare the
    texts (letter case, spaces, the commas in a number), and say why in your notes.
    """
    if answer is None:
        return 0.0
    checks = [dataset_id in answer.get("dataset_ids", []) for dataset_id in expected.get("dataset_ids", [])]
    text = _plain(answer.get("answer", ""))
    checks += [_plain(part) in text for part in expected.get("contains", [])]
    return sum(checks) / len(checks) if checks else 1.0


def _plain(text: str) -> str:
    # Letter case, spaces and the commas in numbers do not count: "50,752" is "50752".
    return re.sub(r"(?<=\d),(?=\d{3})", "", " ".join(str(text).lower().split()))


def _matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    args = actual.get("args") or {}
    return expected["name"] == actual["name"] and all(
        key in args and args[key] == value for key, value in (expected.get("args") or {}).items()
    )


def path_score(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> float:
    """The score of the path of one task, from 0.0 to 1.0.

    The definition of this lab: the share of the expected tool calls that appear in the
    actual calls in the same order. Find the longest list of expected calls that appear in
    the actual calls in their order (a longest common subsequence), and divide its length by
    the number of expected calls.

    An actual call matches an expected call when the names are equal and each argument that
    the expected call names has the same value in the actual call. Arguments that the
    expected call does not name do not count. Extra actual calls do not lower the score. An
    empty list of expected calls scores 1.0.

    Each call is a dict with `name` and, optionally, `args`.
    """
    if not expected:
        return 1.0
    # longest[i][j]: the longest common subsequence of expected[i:] and actual[j:].
    longest = [[0] * (len(actual) + 1) for _ in range(len(expected) + 1)]
    for i in range(len(expected) - 1, -1, -1):
        for j in range(len(actual) - 1, -1, -1):
            if _matches(expected[i], actual[j]):
                longest[i][j] = longest[i + 1][j + 1] + 1
            else:
                longest[i][j] = max(longest[i + 1][j], longest[i][j + 1])
    return longest[0][0] / len(expected)


def load_tasks(path: Path = TASKS) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _events(events: Any, row: dict[str, Any]) -> list[str]:
    """Read the events of one stream into the row. Return the approvals that the stream asks for."""
    approvals = []
    for event, data in events:
        if event == "tool":
            row["calls"].append({"name": data["name"], "args": data["input"]})
        elif event == "answer":
            row["answer"] = data
        elif event == "approval":
            approvals.append(data["name"])
        elif event == "error":
            row["errors"].append(data.get("message", ""))
        elif event == "done":
            row["requests"] += data.get("requests", 0)
            row["cost_usd"] += data.get("cost_usd", 0.0)
    return approvals


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    """Run one task through the graph and return its row, with the two scores."""
    from assistant.graph import answer_events, resume_events

    conversation_id = str(uuid.uuid4())
    row: dict[str, Any] = {"id": task["id"], "task": task["task"], "conversation_id": conversation_id,
                           "answer": None, "calls": [], "refused": [], "errors": [], "requests": 0, "cost_usd": 0.0}
    langfuse = get_client()
    with langfuse.start_as_current_observation(as_type="span", name="agent-task", input={"task_id": task["id"]}) as span:
        with propagate_attributes(trace_name="agent-task", tags=["agent-eval"], metadata={"task_id": task["id"]}):
            row["trace_id"] = langfuse.get_current_trace_id()
            pending = _events(answer_events(task["task"], conversation_id=conversation_id, user=USER), row)
            # The evaluation never approves a write action: it refuses, and the agent goes on.
            for _ in range(5):
                if not pending:
                    break
                row["refused"] += pending
                pending = _events(resume_events(conversation_id, approved=False, approver=USER), row)
        span.update(output=row["answer"] or {"errors": row["errors"]})
    row["result_score"] = result_score(task["expected_result"], row["answer"])
    row["path_score"] = path_score(task["expected_tools"], row["calls"])
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", type=Path, default=TASKS)
    parser.add_argument("--ids", help="Comma-separated task IDs. Default: all tasks.")
    parser.add_argument("--out", type=Path, default=RESULTS / "agent-tasks.json")
    parser.add_argument("--min-result", type=float, help="Exit 1 when the mean result score is below this.")
    parser.add_argument("--min-path", type=float, help="Exit 1 when the mean path score is below this.")
    args = parser.parse_args()

    tasks = load_tasks(args.tasks)
    if args.ids:
        wanted = set(args.ids.split(","))
        tasks = [task for task in tasks if task["id"] in wanted]
    rows = []
    for task in tasks:
        row = run_task(task)
        rows.append(row)
        print(f"{row['id']:5} result {row['result_score']:.2f}  path {row['path_score']:.2f}  "
              f"{len(row['calls'])} calls  ${row['cost_usd']:.5f}", flush=True)
    get_client().flush()
    count = len(rows) or 1
    result = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result_score": sum(row["result_score"] for row in rows) / count,
        "path_score": sum(row["path_score"] for row in rows) / count,
        "cost_usd": sum(row["cost_usd"] for row in rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"result {result['result_score']:.2f}  path {result['path_score']:.2f}  over {len(rows)} tasks  "
          f"cost ${result['cost_usd']:.4f}  results in {args.out}")
    low = [name for name, score, minimum in (("result", result["result_score"], args.min_result),
                                              ("path", result["path_score"], args.min_path))
           if minimum is not None and score < minimum]
    if low:
        sys.exit(f"The {' and the '.join(low)} score is below the minimum.")


if __name__ == "__main__":
    main()
