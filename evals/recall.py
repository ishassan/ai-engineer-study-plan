"""Measure the recall of the retrieval. Weeks 5 and 6.

    make recall                        all three modes
    make recall ARGS="--modes vector"  one mode (week 5)

Arguments:
    --modes LIST      modes of retrieve(), with commas between them. Default: vector,hybrid,rerank
    --k NUMBER        the number of results for each question. Default: 5
    --questions PATH  default: evals/retrieval_questions.jsonl
    --out PATH        default: evals/results/recall.json

For each question and each mode, call retrieve(question, mode, k). A question is
found when at least one of its expected chunk ids is in the results. The recall
of a group of questions is the number of found questions divided by the number
of questions.

Write one JSON file, and print the recall table:

    {
      "k": 5,
      "questions": 50,
      "recall": {"vector": {"ar": 0.8, "en": 0.88, "all": 0.84}, "hybrid": {...}, "rerank": {...}},
      "rows": [
        {"id": "r01", "language": "en", "mode": "vector", "found": true,
         "expected_chunk_ids": ["..."], "retrieved_chunk_ids": ["...", "..."]}
      ]
    }

`rows` has one item for each question and each mode.
"""

from __future__ import annotations

from typing import Any


def measure(questions: list[dict[str, Any]], modes: list[str], k: int = 5) -> dict[str, Any]:
    """Run each question in each mode and return the result in the form above."""
    raise NotImplementedError("Week 5, step 4")


def main() -> None:
    raise NotImplementedError("Week 5, step 4")


if __name__ == "__main__":
    main()
