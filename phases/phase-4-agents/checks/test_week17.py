"""Week 17 checks: the agent tasks, the two scores, the runner, the result file and the CI step.

Run them with `make check WEEK=17`. The runner checks use the fake Claude API and your two MCP
servers (started by the checks, see conftest.py), so they are free. Postgres must run
(`make up`). The result file comes from `make agent-eval` (real Claude API). The workflow
check runs actionlint in Docker (image rhysd/actionlint:1.7.12).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from phase4_helpers import mcp_tools

from labkit.fake_claude import first_user_text, json_reply, tool_reply

REPO = Path(__file__).resolve().parents[3]
TASKS = REPO / "evals" / "agent_tasks.jsonl"
RESULT = REPO / "evals" / "results" / "agent-tasks.json"
WORKFLOW = REPO / ".github" / "workflows" / "evals.yml"
ACTIONLINT = "rhysd/actionlint:1.7.12"
CEMENT = "cement-production-and-sales"
LOCAL_TOOLS = {"search_documents", "save_memory"}


@pytest.fixture(autouse=True)
def graph(monkeypatch):
    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("AGENT_PLANNER", "off")
    monkeypatch.setenv("PROVIDER", "anthropic")


def load_tasks() -> list[dict[str, Any]]:
    assert TASKS.exists(), "evals/agent_tasks.jsonl does not exist. Run `make start PHASE=4`."
    return [json.loads(line) for line in TASKS.read_text(encoding="utf-8").splitlines() if line.strip()]


def call(name: str, **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args} if args else {"name": name}


# ---- step 3: the two scores (unit checks) --------------------------------------------------

A, B, C = call("search_datasets"), call("get_dataset_schema", dataset_id=CEMENT), call("run_sql")

PATHS = [
    ("the same calls in the same order", [A, B, C], [A, B, C], 1.0),
    ("one expected call is missing", [A, B, C], [A, C], 2 / 3),
    ("two calls in the other order", [A, B], [B, A], 0.5),
    ("extra calls do not lower the score", [A, B], [call("get_dataset_stats", dataset_id=CEMENT), A, C, B, C], 1.0),
    ("a named argument with another value does not match", [A, B], [A, call("get_dataset_schema", dataset_id="other")], 0.5),
    ("arguments that the expected call does not name do not count",
     [A, B], [call("search_datasets", query="cement", limit=3), call("get_dataset_schema", dataset_id=CEMENT, x=1)], 1.0),
    ("the longest list in order, not the first match", [A, B, C], [B, C, A], 2 / 3),
    ("an expected call matches one actual call only", [A, A], [A], 0.5),
    ("no actual calls", [A, B], [], 0.0),
    ("no expected calls", [], [A], 1.0),
]


@pytest.mark.parametrize("case, expected, actual, score", PATHS, ids=[row[0] for row in PATHS])
def test_the_path_score(case, expected, actual, score):
    from evals.agent_eval import path_score

    assert path_score(expected, actual) == pytest.approx(score), f"{case}: expected {score:.2f}."


def test_the_result_score():
    from evals.agent_eval import result_score

    expected = {"dataset_ids": [CEMENT], "contains": ["112", "Saudi Central Bank"]}
    good = {"answer": "It has 112 records and Saudi Central Bank publishes it.", "dataset_ids": [CEMENT, "other"]}
    assert result_score(expected, None) == 0.0, "No answer scores 0.0."
    assert result_score(expected, good) == pytest.approx(1.0), "An answer that meets each expectation scores 1.0."
    assert result_score(expected, {**good, "dataset_ids": []}) < 1.0, "A missing dataset ID lowers the score."
    assert result_score(expected, {**good, "answer": "It has 112 records."}) < 1.0, "A missing text lowers the score."
    assert result_score(expected, {"answer": "No idea.", "dataset_ids": []}) == pytest.approx(0.0)
    assert 0.0 <= result_score(expected, {**good, "dataset_ids": []}) <= 1.0
    assert result_score({"dataset_ids": [], "contains": []}, good) == pytest.approx(1.0)


# ---- the runner with the fake API -----------------------------------------------------------

TASK = {
    "id": "check-1",
    "task": "How many records does the cement dataset have? (a task of the checks)",
    "expected_result": {"dataset_ids": [CEMENT], "contains": ["112"]},
    "expected_tools": [call("search_datasets"), call("get_dataset_stats", dataset_id=CEMENT)],
}


def final(text: str, ids: list[str]):
    return json_reply({"answer": text, "dataset_ids": ids, "tools_called": []})


def test_the_runner_scores_a_correct_path(fake, mcp, database):
    from evals.agent_eval import run_task

    fake.script(
        tool_reply(("search_datasets", {"query": "cement"})),
        tool_reply(("get_dataset_stats", {"dataset_id": CEMENT})),
        final("The cement dataset has 112 records.", [CEMENT]),
    )
    row = run_task(TASK)
    assert [c["name"] for c in row["calls"]] == ["search_datasets", "get_dataset_stats"], row["calls"]
    assert (row["result_score"], row["path_score"]) == (pytest.approx(1.0), pytest.approx(1.0)), row


def test_the_runner_scores_a_wrong_path(fake, mcp, database):
    from evals.agent_eval import run_task

    fake.script(tool_reply(("get_dataset_schema", {"dataset_id": "gas-sales-by-region-2001-2013"})),
                final("I could not find it.", []))
    row = run_task(TASK)
    assert (row["result_score"], row["path_score"]) == (pytest.approx(0.0), pytest.approx(0.0)), row


def test_the_runner_scores_a_correct_result_on_a_wrong_path(fake, mcp, database):
    from evals.agent_eval import run_task

    fake.script(tool_reply(("get_dataset_stats", {"dataset_id": CEMENT})), final("It has 112 records.", [CEMENT]))
    row = run_task(TASK)
    assert row["result_score"] == pytest.approx(1.0), row
    assert row["path_score"] == pytest.approx(0.5), "The path missed search_datasets: half of the expected calls."


def test_the_runner_never_approves_the_write_action(fake, mcp, sql, database):
    from evals.agent_eval import run_task

    dataset_id = f"check-{uuid.uuid4().hex[:10]}"
    arguments = {"dataset_id": dataset_id, "title": "A check dataset", "description": "Made by a check.", "owner": "Lab"}
    task = {"id": "check-2", "task": "Register the check dataset.", "expected_result": {"dataset_ids": [], "contains": []},
            "expected_tools": [call("register_dataset", dataset_id=dataset_id)]}
    fake.script(tool_reply(("register_dataset", arguments)), final("The action was refused.", []))
    try:
        row = run_task(task)
        assert row["refused"] == ["register_dataset"], row
        assert row["path_score"] == pytest.approx(1.0), "A refused call is still a call of the path."
        assert sql("SELECT id FROM datasets WHERE id = %s", (dataset_id,)) == [], "The write action ran in the evaluation."
        rows = sql("SELECT approval, approver FROM audit_log WHERE tool = 'register_dataset' AND arguments->>'dataset_id' = %s",
                   (dataset_id,))
        assert rows == [{"approval": "refused", "approver": "agent-eval"}], rows
    finally:
        sql("DELETE FROM datasets WHERE id = %s", (dataset_id,))


def test_the_runner_exits_with_an_error_below_the_minimum(fake, mcp, tmp_path, monkeypatch, database):
    from evals import agent_eval

    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps(TASK) + "\n", encoding="utf-8")
    out = tmp_path / "result.json"

    def reply(body):  # a correct result on a wrong path
        assert first_user_text(body) == TASK["task"]
        return final("It has 112 records.", [CEMENT])

    fake.always(reply)
    monkeypatch.setattr(sys, "argv", ["agent_eval", "--tasks", str(tasks), "--out", str(out), "--min-result", "0.9"])
    agent_eval.main()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert (data["result_score"], data["path_score"], len(data["rows"])) == (pytest.approx(1.0), pytest.approx(0.0), 1)
    monkeypatch.setattr(sys, "argv", ["agent_eval", "--tasks", str(tasks), "--out", str(out), "--min-path", "0.9"])
    with pytest.raises(SystemExit) as stop:
        agent_eval.main()
    assert stop.value.code not in (0, None), "Below --min-path the runner must exit with an error, so CI fails."


# ---- step 2: the 30 tasks -------------------------------------------------------------------


def test_you_wrote_30_multi_step_tasks(mcp, sql, database):
    tasks = load_tasks()
    assert len(tasks) >= 30, f"Write at least 30 tasks. evals/agent_tasks.jsonl has {len(tasks)}."
    assert len({t["id"] for t in tasks}) == len(tasks), "Each task has its own ID."
    assert len({t["task"].strip().lower() for t in tasks}) == len(tasks), "Each task has its own text."
    known = LOCAL_TOOLS | set(mcp_tools(mcp["sql"].url)) | set(mcp_tools(mcp["catalogue"].url))
    datasets = {row["id"] for row in sql("SELECT id FROM datasets")}
    for task in tasks:
        expected, tools = task["expected_result"], task["expected_tools"]
        assert len(tools) >= 2, f"{task['id']}: a multi-step task expects at least two tool calls."
        assert {tool["name"] for tool in tools} <= known, f"{task['id']}: an expected tool does not exist: {tools}"
        assert expected.get("dataset_ids") or expected.get("contains"), f"{task['id']}: give an expected result."
        assert set(expected.get("dataset_ids", [])) <= datasets, f"{task['id']}: a dataset ID is not in the catalogue."
        for tool in tools:
            dataset_id = (tool.get("args") or {}).get("dataset_id")
            if dataset_id and tool["name"] == "register_dataset":
                assert dataset_id not in datasets, f"{task['id']}: register_dataset expects a new dataset ID."
            elif dataset_id:
                assert dataset_id in datasets, f"{task['id']}: {dataset_id} is not in the catalogue."
    names = [{tool["name"] for tool in task["expected_tools"]} for task in tasks]
    assert sum("run_sql" in found for found in names) >= 5, "Write at least 5 tasks that need run_sql."
    assert sum("register_dataset" in found for found in names) >= 2, "Write at least 2 tasks that ask to register a dataset."


# ---- the result file of `make agent-eval` ---------------------------------------------------


def test_the_result_file_scores_each_task_on_the_result_and_the_path(sql, database):
    from evals.agent_eval import path_score, result_score

    tasks = {task["id"]: task for task in load_tasks()}
    assert RESULT.exists(), "evals/results/agent-tasks.json does not exist. Run `make agent-eval`."
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    rows = data["rows"]
    assert sorted(row["id"] for row in rows) == sorted(tasks), "Run all the tasks of evals/agent_tasks.jsonl."
    for row in rows:
        task = tasks[row["id"]]
        assert row["result_score"] == pytest.approx(result_score(task["expected_result"], row["answer"])), (
            f"{row['id']}: result_score in the file does not agree with result_score() of the row."
        )
        assert row["path_score"] == pytest.approx(path_score(task["expected_tools"], row["calls"])), (
            f"{row['id']}: path_score in the file does not agree with path_score() of the row."
        )
        for tool in task["expected_tools"]:
            if tool["name"] == "register_dataset" and "register_dataset" in [c["name"] for c in row["calls"]]:
                assert "register_dataset" in row["refused"], f"{row['id']}: the evaluation must refuse the write action."
    assert data["result_score"] == pytest.approx(sum(r["result_score"] for r in rows) / len(rows)), (
        "result_score of the file is the mean of the rows."
    )
    assert data["path_score"] == pytest.approx(sum(r["path_score"] for r in rows) / len(rows)), (
        "path_score of the file is the mean of the rows."
    )
    new_ids = [(tool.get("args") or {}).get("dataset_id") for task in tasks.values() for tool in task["expected_tools"]
               if tool["name"] == "register_dataset"]
    assert sql("SELECT id FROM datasets WHERE id = ANY(%s)", ([i for i in new_ids if i],)) == [], (
        "A dataset of a register task is in the catalogue: the write action ran without approval."
    )
    print(f"\n  result {data['result_score']:.2f}   path {data['path_score']:.2f}   over {len(rows)} tasks")


# ---- step 3: the CI step ----------------------------------------------------------------------


def test_the_workflow_runs_the_agent_tasks():
    assert WORKFLOW.exists(), ".github/workflows/evals.yml does not exist (week 11)."
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "agent-eval" in text or "evals.agent_eval" in text, "Add a step that runs the agent tasks."
    assert "--min-result" in text and "--min-path" in text, "Give both minimum scores, so a worse agent fails CI."
    assert "mcp-sql" in text and "mcp-catalogue" in text, "Start the two MCP servers in the job."
    assert "phase4" in text and "load_tables" in text, "Install the packages of phase 4 and load the data tables."
    docker = shutil.which("docker")
    assert docker, "Docker is not on the PATH. The check runs actionlint in Docker."
    process = subprocess.run(
        [docker, "run", "--rm", "-v", f"{REPO}:/repo:ro", "-w", "/repo", ACTIONLINT, "-color=false",
         ".github/workflows/evals.yml"],
        capture_output=True, text=True, timeout=300,
    )
    assert process.returncode == 0, f"actionlint found problems in the workflow:\n{process.stdout}{process.stderr}"
