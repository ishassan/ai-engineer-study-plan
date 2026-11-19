"""Reference solution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evals" / "retrieval_questions.jsonl"
OUT = ROOT / "evals" / "results" / "recall.json"


def load_questions(path: Path = QUESTIONS) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def measure(questions: list[dict[str, Any]], modes: list[str], k: int = 5) -> dict[str, Any]:
    from assistant.retrieval import retrieve

    rows = []
    for mode in modes:
        for question in questions:
            retrieved = [row["chunk_id"] for row in retrieve(question["question"], mode, k)]
            rows.append(
                {
                    "id": question["id"],
                    "language": question["language"],
                    "mode": mode,
                    "found": bool(set(question["expected_chunk_ids"]) & set(retrieved)),
                    "expected_chunk_ids": question["expected_chunk_ids"],
                    "retrieved_chunk_ids": retrieved,
                }
            )
    recall: dict[str, dict[str, float]] = {}
    for mode in modes:
        of_mode = [row for row in rows if row["mode"] == mode]
        groups = {"all": of_mode}
        for language in sorted({row["language"] for row in of_mode}):
            groups[language] = [row for row in of_mode if row["language"] == language]
        recall[mode] = {
            name: sum(row["found"] for row in group) / len(group) for name, group in groups.items() if group
        }
    return {"k": k, "questions": len(questions), "recall": recall, "rows": rows}


def format_table(result: dict[str, Any]) -> str:
    lines = [f"Recall in the top {result['k']} ({result['questions']} questions)", ""]
    lines.append(f"{'mode':10} {'ar':>6} {'en':>6} {'all':>6}")
    for mode, values in result["recall"].items():
        cells = " ".join(f"{values.get(name, float('nan')):6.2f}" for name in ("ar", "en", "all"))
        lines.append(f"{mode:10} {cells}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default="vector,hybrid,rerank")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    result = measure(load_questions(args.questions), args.modes.split(","), args.k)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(format_table(result))
    print(f"\nresults in {args.out}")


if __name__ == "__main__":
    main()
