"""Week 11 checks: the CI workflow, the snapshot of the chunks, and your evaluation suite.

Run them with `make check WEEK=11`. The checks run your suite `tests/evals` five times in a
separate process, against the fake Claude API of the lab: one time with good answers, and
four times with answers that are worse in one way. Your suite must pass the first run and
fail the four others. This is the exit test of the phase without the real API: a worse
change must not pass CI.

Postgres and both model services must run (`make up`). Langfuse is not needed. The runs with searches
re-rank real chunks, so on a slow CPU this file takes some minutes.
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Callable

import pytest

from labkit.fake_claude import first_user_text, json_reply, tool_reply

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "evals.yml"
SNAPSHOT = REPO / "data" / "snapshot" / "chunks.sql.gz"
SUITE = REPO / "tests" / "evals"
MAX_CASES = 15
INVENTED_CHUNK = "gastat-no-such-document-en:p1:c1"
WRONG_DATASET = "no-such-dataset-in-the-catalogue"


def ci_cases(testset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [case for case in testset if case.get("ci")]


def tool_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    """The results of search_documents in the messages of a request."""
    found = []
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
                found += [item for item in data if isinstance(item, dict) and "chunk_id" in item]
    return found


def verdict(body: dict[str, Any], passed: bool):
    schema = ((body.get("output_config") or {}).get("format") or {}).get("schema") or {}
    value = {
        name: passed if field.get("type") == "boolean" else ([] if field.get("type") == "array" else "The rubric decides.")
        for name, field in (schema.get("properties") or {}).items()
    }
    return json_reply(value or {"passed": passed})


def policy(cases: list[dict[str, Any]], mode: str) -> Callable[[dict[str, Any]], Any]:
    """The fake model for one run of the suite.

    good: the agent searches, then names the expected datasets and cites the returned
    chunks (the expected chunk first, when the search returned it); the grader passes.
    wrong_datasets: like good, but each answer names a wrong dataset ID.
    invented_citations: the agent cites a chunk ID that no search returned, without a search.
    wrong_chunk_cited: like good, but the answer cites a returned chunk that is not expected.
    grader_fails: like good, but the grader fails each output.
    """
    by_question = {case["question"]: case for case in cases}

    def reply(body: dict[str, Any]):
        if not body.get("tools"):  # The grader sends no tools.
            return verdict(body, passed=mode != "grader_fails")
        case = by_question.get(first_user_text(body))
        if case is None:
            return json_reply({"answer": "I do not know.", "dataset_ids": [], "tools_called": []})
        searched = any(message["role"] == "assistant" for message in body["messages"])
        if not searched and mode != "invented_citations":
            if case.get("expected_chunk_ids"):
                return tool_reply(("search_documents", {"query": case["question"]}))
            return tool_reply(("search_datasets", {"query": case["question"]}))
        ids = list(case.get("expected_dataset_ids", []))
        if mode == "wrong_datasets" and ids:
            ids = [WRONG_DATASET]
        citations = []
        if mode == "invented_citations" and case.get("expected_chunk_ids"):
            citations = [{"document_title": "No such document", "page": 1, "chunk_id": INVENTED_CHUNK}]
        elif case.get("expected_chunk_ids"):
            returned = tool_results(body)
            expected = [r for r in returned if r["chunk_id"] in case["expected_chunk_ids"]]
            others = [r for r in returned if r["chunk_id"] not in case["expected_chunk_ids"]]
            chosen = (others if mode == "wrong_chunk_cited" else expected or returned)[:1]
            citations = [{"document_title": r["title"], "page": r["page"], "chunk_id": r["chunk_id"]} for r in chosen]
        tools = ["search_documents"] if case.get("expected_chunk_ids") else ["search_datasets"]
        return json_reply({"answer": "The answer of the fake model.", "dataset_ids": ids, "tools_called": tools, "citations": citations})

    return reply


def run_suite(fake, cases: list[dict[str, Any]], mode: str, tmp_path: Path) -> dict[str, Any]:
    """Run tests/evals in a new process against the fake API, and read the result."""
    fake.always(policy(cases, mode))
    report = tmp_path / f"{mode}.xml"
    env = dict(
        os.environ,
        ANTHROPIC_BASE_URL=fake.url,
        ANTHROPIC_API_KEY="offline-check-key",
        RESPONSE_CACHE="on",
        RESPONSE_CACHE_DIR=str(tmp_path / f"cache-{mode}"),
        REQUEST_LOG_PATH=str(tmp_path / f"requests-{mode}.jsonl"),
    )
    command = [sys.executable, "-m", "pytest", str(SUITE), "-p", "no:labkit.plugin", "-p", "no:cacheprovider",
               f"--junitxml={report}", "-q"]
    process = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, timeout=1800)
    tests = []
    if report.exists():
        for case in ElementTree.parse(report).getroot().iter("testcase"):
            outcome = "passed"
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            tests.append((case.get("name"), outcome))
    return {"code": process.returncode, "tests": tests, "output": process.stdout[-3000:] + process.stderr[-2000:]}


@pytest.fixture(scope="module")
def suite_cases(testset) -> list[dict[str, Any]]:
    cases = ci_cases(testset)
    assert cases, 'Mark the cases of the CI subset with "ci": true in evals/testset.jsonl.'
    return cases


# ---- the workflow and the snapshot ----------------------------------------------------------


def test_the_workflow_runs_the_suite_on_each_pull_request():
    assert WORKFLOW.exists(), ".github/workflows/evals.yml does not exist. Run `make start PHASE=3`."
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request" in text, "The workflow must run on each pull request."
    assert "secrets.ANTHROPIC_API_KEY" in text, "The suite needs the secret ANTHROPIC_API_KEY."
    assert "make restore" in text, "Restore the chunks from the snapshot, so CI does not embed the documents again."
    assert "make evals" in text or "tests/evals" in text, "The workflow must run the suite tests/evals."


def test_the_snapshot_holds_each_chunk_with_its_vector(sql):
    assert SNAPSHOT.exists(), "data/snapshot/chunks.sql.gz does not exist. Run `make snapshot`, then commit the file."
    ids, without_vector, inside = set(), [], False
    with gzip.open(SNAPSHOT, "rt", encoding="utf-8") as file:
        for line in file:
            if line.startswith("COPY public.chunks "):
                columns = line[line.index("(") + 1 : line.index(")")].replace('"', "").split(", ")
                inside = True
                continue
            if inside:
                if line.startswith("\\."):
                    break
                values = line.rstrip("\n").split("\t")
                row = dict(zip(columns, values))
                ids.add(row["id"])
                if not any(len(value) > 1000 and value.startswith("[") for value in values):
                    without_vector.append(row["id"])
    stored = {row["id"] for row in sql("SELECT id FROM chunks")}
    assert ids, "The snapshot has no chunks. Run `make snapshot` when the chunks are in Postgres."
    assert ids == stored, (
        f"The snapshot has {len(ids)} chunks and Postgres has {len(stored)}. Run `make snapshot` again "
        "after each `make ingest`."
    )
    assert not without_vector, f"{len(without_vector)} chunks of the snapshot have no vector. Run `make embed`, then `make snapshot`."


def test_the_ci_subset_is_fixed_and_small(suite_cases):
    assert len(suite_cases) <= MAX_CASES, f"The CI subset has {len(suite_cases)} cases. Keep at most {MAX_CASES}."
    assert any(case.get("expected_dataset_ids") for case in suite_cases), "Put cases about datasets in the CI subset."
    assert any(case.get("expected_chunk_ids") for case in suite_cases), "Put cases about the documents in the CI subset."


# ---- the suite: it passes good answers and blocks worse ones ---------------------------------


def test_the_suite_passes_with_good_answers(fake, suite_cases, services, tmp_path):
    result = run_suite(fake, suite_cases, "good", tmp_path)
    failed = [name for name, outcome in result["tests"] if outcome == "failed"]
    assert result["tests"], f"The suite ran no test.\n{result['output']}"
    assert result["code"] == 0 and not failed, (
        f"With good answers, these tests of the suite failed: {failed}. Check the scores and the "
        f"thresholds.\n{result['output']}"
    )
    assert sum(outcome == "passed" for _, outcome in result["tests"]) >= 3, (
        "Write one test for each score: dataset IDs, citations and the grader."
    )


@pytest.mark.parametrize(
    "mode, what",
    [
        ("wrong_datasets", "each answer names a wrong dataset ID"),
        ("invented_citations", "the model cites a chunk that no search returned"),
        ("wrong_chunk_cited", "each answer cites a returned chunk, but not the expected one"),
        ("grader_fails", "the grader fails each output, and the code checks pass"),
    ],
)
def test_the_suite_fails_when_the_answers_are_worse(fake, suite_cases, services, tmp_path, mode, what):
    result = run_suite(fake, suite_cases, mode, tmp_path)
    assert result["tests"], f"The suite ran no test.\n{result['output']}"
    assert result["code"] != 0, (
        f"The suite passed when {what}. A score of the suite must fall below its threshold, so "
        f"that CI blocks this change.\n{result['output']}"
    )
