"""Reference solution: the evaluation suite of CI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from assistant.config import get_settings
from evals.grader import grade
from evals.run_testset import load_cases, run_case

MAX_CASES = 15
# Thresholds: the share of the cases that must pass each score.
DATASET_IDS_THRESHOLD = 0.8
CITATIONS_THRESHOLD = 0.75
GRADER_THRESHOLD = 0.8

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def cases() -> list[dict[str, Any]]:
    chosen = [case for case in load_cases() if case.get("ci")]
    assert 1 <= len(chosen) <= MAX_CASES, f"Mark 1 to {MAX_CASES} cases with \"ci\": true. Now: {len(chosen)}."
    return chosen


@pytest.fixture(scope="session")
def rows(cases) -> list[dict[str, Any]]:
    """Run each case one time for the whole session."""
    results = [run_case(case, run_name="ci") for case in cases]
    out = ROOT / "evals" / "results" / "ci.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results), encoding="utf-8")
    return results


def report(name: str, passed: list[bool], threshold: float) -> float:
    score = sum(passed) / len(passed)
    print(f"\n{name}: {score:.2f} over {len(passed)} cases (threshold {threshold:.2f})")
    return score


def test_the_answers_name_the_expected_datasets(rows):
    chosen = [row for row in rows if row["expected_dataset_ids"]]
    if not chosen:
        pytest.skip("No CI case has expected dataset IDs.")
    passed = [row["answer"] is not None and set(row["expected_dataset_ids"]) <= set(row["dataset_ids"]) for row in chosen]
    score = report("dataset IDs", passed, DATASET_IDS_THRESHOLD)
    assert score >= DATASET_IDS_THRESHOLD, [row["id"] for row, ok in zip(chosen, passed) if not ok]


def test_the_citations_are_valid_and_cite_an_expected_chunk(rows):
    chosen = [row for row in rows if row["expected_chunk_ids"]]
    if not chosen:
        pytest.skip("No CI case has expected chunk IDs.")
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as connection:
        stored = {
            row["id"]: row
            for row in connection.execute(
                "SELECT c.id, c.page, d.title FROM chunks c JOIN documents d ON d.id = c.document_id"
            ).fetchall()
        }

    def valid(row: dict[str, Any]) -> bool:
        citations = row["citations"]
        if row["answer"] is None or not citations:
            return False
        for citation in citations:
            chunk = stored.get(citation.get("chunk_id"))
            if chunk is None or chunk["page"] != citation.get("page") or chunk["title"] != citation.get("document_title"):
                return False
        return bool({c["chunk_id"] for c in citations} & set(row["expected_chunk_ids"]))

    passed = [valid(row) for row in chosen]
    score = report("citations", passed, CITATIONS_THRESHOLD)
    assert score >= CITATIONS_THRESHOLD, [row["id"] for row, ok in zip(chosen, passed) if not ok]


def test_the_grader_passes_the_outputs(rows):
    passed = [row["answer"] is not None and grade(row).passed for row in rows]
    score = report("grader", passed, GRADER_THRESHOLD)
    assert score >= GRADER_THRESHOLD, [row["id"] for row, ok in zip(rows, passed) if not ok]
