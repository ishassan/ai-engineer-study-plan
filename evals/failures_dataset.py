"""Send the failing cases of your error analysis to a Langfuse dataset. Week 9, step 4.

This file is complete.

    make failures-dataset

It reads evals/error_notes.jsonl (your notes from the notebook) and evals/testset.jsonl. For
each note with "passed": false, it writes one item to the Langfuse dataset
"assistant-failures":

    input            {"question": ..., "language": ...}
    expected_output  {"dataset_ids": [...], "chunk_ids": [...]}
    metadata         {"case_id": ..., "category": ..., "note": ...}
    source trace     the trace that you read

The ID of an item comes from the case ID, so a second run updates the same items and adds
no copies.
"""

from __future__ import annotations

import json
from pathlib import Path

from langfuse import get_client

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "evals" / "error_notes.jsonl"
TESTSET = ROOT / "evals" / "testset.jsonl"
DATASET_NAME = "assistant-failures"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    cases = {case["id"]: case for case in read_jsonl(TESTSET)}
    failures = [note for note in read_jsonl(NOTES) if note.get("passed") is False]
    langfuse = get_client()
    if not langfuse.auth_check():
        raise SystemExit("Langfuse does not accept the keys in .env. Run `make up` and check LANGFUSE_* in .env.")
    try:
        langfuse.get_dataset(DATASET_NAME)
    except Exception:
        langfuse.create_dataset(
            name=DATASET_NAME,
            description="Failing cases of the error analysis of week 9, with the expected results.",
        )
    for note in failures:
        case = cases[note["case_id"]]
        langfuse.create_dataset_item(
            dataset_name=DATASET_NAME,
            id=f"{DATASET_NAME}-{case['id']}",
            input={"question": case["question"], "language": case.get("language")},
            expected_output={
                "dataset_ids": case.get("expected_dataset_ids", []),
                "chunk_ids": case.get("expected_chunk_ids", []),
            },
            metadata={"case_id": case["id"], "category": note.get("category", ""), "note": note.get("note", "")},
            source_trace_id=note.get("trace_id"),
        )
    langfuse.flush()
    print(f"{len(failures)} failing cases are in the Langfuse dataset {DATASET_NAME!r}.")


if __name__ == "__main__":
    main()
