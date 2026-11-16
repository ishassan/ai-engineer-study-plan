"""Week 17 live check: three agent tasks on the real Claude API, through your MCP servers.

Run it with `make check-live WEEK=17`. It calls the real Claude API, so it costs money: about
$0.01 for the three tasks (estimate: about 10 requests of about 3,000 input tokens at the
prices of Claude Haiku 5.5). It needs ANTHROPIC_API_KEY in your `.env` file, Postgres with the
tables of the schema `data` (`make up`). The checks start your two MCP servers (see
conftest.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TASKS = Path(__file__).resolve().parents[3] / "evals" / "agent_tasks.jsonl"


def test_three_tasks_are_scored_and_the_write_action_is_refused(live, mcp, sql, database, monkeypatch):
    from evals.agent_eval import run_task

    monkeypatch.setenv("AGENT_PLANNER", "off")
    tasks = [json.loads(line) for line in TASKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    chosen = [task for task in tasks if task["id"] in {"a01", "a02", "a03"}] or tasks[:3]
    for task in chosen:
        row = run_task(task)
        assert 0.0 <= row["result_score"] <= 1.0 and 0.0 <= row["path_score"] <= 1.0, row
        assert row["answer"] is not None, f"{task['id']}: no answer. Errors: {row['errors']}"
        assert row["cost_usd"] > 0
        if "register_dataset" in [call["name"] for call in row["calls"]]:
            assert "register_dataset" in row["refused"], f"{task['id']}: the write action was not refused."
        print(f"\n  {task['id']}  result {row['result_score']:.2f}  path {row['path_score']:.2f}  "
              f"{[call['name'] for call in row['calls']]}  ${row['cost_usd']:.5f}")
    new_ids = [(tool.get("args") or {}).get("dataset_id") for task in chosen for tool in task["expected_tools"]
               if tool["name"] == "register_dataset"]
    assert sql("SELECT id FROM datasets WHERE id = ANY(%s)", ([i for i in new_ids if i],)) == []
