"""Week 9 checks: the test set, your notes of the error analysis, the table of failure
categories, and the Langfuse dataset of the failing cases.

Run them with `make check WEEK=9`. They read files in evals/, your Postgres database and
Langfuse. They call no model.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
NOTES = REPO / "evals" / "error_notes.jsonl"
TABLE = REPO / "evals" / "failure_categories.csv"
DATASET_NAME = "assistant-failures"
ARABIC = re.compile("[؀-ۿ]")
TRACE_ID = re.compile("^[0-9a-f]{32}$")


def read_jsonl(path: Path) -> list[dict]:
    import json

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def notes() -> list[dict]:
    assert NOTES.exists(), (
        "evals/error_notes.jsonl does not exist. Read your traces in the notebook "
        "phases/phase-3-evaluation/notebooks/error_analysis.ipynb and save a note for each (step 3)."
    )
    return read_jsonl(NOTES)


@pytest.fixture(scope="module")
def failures(notes) -> list[dict]:
    return [note for note in notes if note.get("passed") is False]


# ---- step 2: the test set ---------------------------------------------------------------------


def test_the_test_set_has_more_than_100_cases(testset):
    assert len(testset) > 100, (
        f"evals/testset.jsonl has {len(testset)} cases. The plan asks for more than 100. Draft the "
        "questions with Claude Code, then correct each one by hand (step 2)."
    )


def test_each_case_has_its_fields(testset):
    ids = [case.get("id") for case in testset]
    assert len(set(ids)) == len(ids), "Each case needs its own id."
    for case in testset:
        assert case.get("language") in {"en", "ar"}, f"{case.get('id')}: language is 'en' or 'ar'."
        assert isinstance(case.get("question"), str) and case["question"].strip(), f"{case['id']}: no question."
        for key in ("expected_dataset_ids", "expected_chunk_ids"):
            assert isinstance(case.get(key, []), list), f"{case['id']}: {key} is a list."


def test_the_cases_are_in_english_and_arabic(testset):
    english = [case for case in testset if case["language"] == "en"]
    arabic = [case for case in testset if case["language"] == "ar"]
    assert len(english) >= 25 and len(arabic) >= 25, (
        f"The test set has {len(english)} English and {len(arabic)} Arabic cases. Write at least 25 of each."
    )
    without = [case["id"] for case in arabic if not ARABIC.search(case["question"])]
    assert not without, f"These Arabic cases have no Arabic letters: {without}"


def test_the_questions_are_different(testset):
    seen: dict[str, str] = {}
    for case in testset:
        key = " ".join(case["question"].lower().split())
        assert key not in seen, f"{case['id']} has the same question as {seen[key]}."
        seen[key] = case["id"]
    both = [case for case in testset if case.get("expected_dataset_ids")]
    documents = [case for case in testset if case.get("expected_chunk_ids")]
    assert len(both) >= 10 and len(documents) >= 10, (
        "Use the two kinds of questions of the assistant: at least 10 cases about datasets "
        "(expected_dataset_ids) and 10 about the documents (expected_chunk_ids)."
    )


def test_the_expected_ids_exist(testset, sql):
    dataset_ids = sorted({i for case in testset for i in case.get("expected_dataset_ids", [])})
    chunk_ids = sorted({i for case in testset for i in case.get("expected_chunk_ids", [])})
    known_datasets = {row["id"] for row in sql("SELECT id FROM datasets WHERE id = ANY(%s)", (dataset_ids,))}
    known_chunks = {row["id"] for row in sql("SELECT id FROM chunks WHERE id = ANY(%s)", (chunk_ids,))}
    wrong = sorted(set(dataset_ids) - known_datasets) + sorted(set(chunk_ids) - known_chunks)
    assert not wrong, f"These expected IDs are not in Postgres: {wrong[:10]}. A wrong ID makes a correct answer fail."


# ---- step 3: open coding and axial coding -----------------------------------------------------


def test_you_read_at_least_30_traces(notes, testset):
    case_ids = [note.get("case_id") for note in notes]
    assert len(set(case_ids)) == len(case_ids), "Keep one note for each case."
    assert len(notes) >= 30, f"You saved {len(notes)} notes. Read at least 30 traces (step 3)."
    unknown = sorted(set(case_ids) - {case["id"] for case in testset})
    assert not unknown, f"These notes name cases that are not in the test set: {unknown}"
    for note in notes:
        assert isinstance(note.get("passed"), bool), f"{note['case_id']}: passed is true or false."
        assert TRACE_ID.match(str(note.get("trace_id"))), f"{note['case_id']}: the trace_id of the trace that you read."


def test_each_failure_has_a_note_and_a_category(failures):
    assert failures, "None of your notes is a failure. Read more traces, or read them more strictly."
    for note in failures:
        assert len(str(note.get("note", "")).split()) >= 3, (
            f"{note['case_id']}: write a short note on what went wrong first (open coding)."
        )
        assert str(note.get("category", "")).strip(), (
            f"{note['case_id']}: put each failure into a category (axial coding)."
        )


def test_the_table_of_categories_counts_the_notes(failures):
    assert TABLE.exists(), "evals/failure_categories.csv does not exist. Run the last cell of the notebook."
    with TABLE.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert rows and {"category", "count", "description"} <= set(rows[0]), (
        "The table has the columns category, count and description."
    )
    table = {row["category"]: int(row["count"]) for row in rows}
    counted: dict[str, int] = {}
    for note in failures:
        counted[note["category"]] = counted.get(note["category"], 0) + 1
    assert table == counted, f"The table does not agree with the notes. Table: {table}. Notes: {counted}"
    counts = [int(row["count"]) for row in rows]
    assert counts == sorted(counts, reverse=True), "Put the largest category first."
    empty = [row["category"] for row in rows if not row["description"].strip()]
    assert not empty, f"Describe each category: {empty}"


# ---- step 4: the Langfuse dataset ------------------------------------------------------------


def test_the_failing_cases_are_in_the_langfuse_dataset(failures, testset, langfuse):
    items, page = [], 1
    while True:
        try:
            response = langfuse.get("/api/public/dataset-items", datasetName=DATASET_NAME, page=page, limit=100)
        except Exception as error:
            pytest.fail(f"The dataset {DATASET_NAME!r} does not exist in Langfuse. Run `make failures-dataset`.\n{error}")
        items += response["data"]
        if page >= response["meta"]["totalPages"]:
            break
        page += 1
    by_case = {(item.get("metadata") or {}).get("case_id"): item for item in items}
    cases = {case["id"]: case for case in testset}
    missing = [note["case_id"] for note in failures if note["case_id"] not in by_case]
    assert not missing, f"These failing cases are not in the dataset: {missing}. Run `make failures-dataset`."
    for note in failures:
        expected = by_case[note["case_id"]].get("expectedOutput") or {}
        case = cases[note["case_id"]]
        assert sorted(expected.get("dataset_ids", [])) == sorted(case.get("expected_dataset_ids", [])), (
            f"{note['case_id']}: the expected result in Langfuse is old. Run `make failures-dataset` again."
        )
        assert sorted(expected.get("chunk_ids", [])) == sorted(case.get("expected_chunk_ids", []))
