"""Week 2 live check: your 5 quick questions go through the real model loop.

Run it with `make check-live WEEK=2`. It makes about 15 real requests, which
cost about $0.01.
"""

from __future__ import annotations

import json

from labkit.sse import ask


def test_the_quick_questions_use_tools_and_name_the_expected_datasets(client, live, questions, database, capsys):
    quick = [question for question in questions if question.get("quick")]
    assert len(quick) == 5, "Mark 5 questions with \"quick\": true (week 1, step 6)."

    rows = []
    for question in quick:
        result = ask(client, question["question"])
        assert result.status_code == 200
        done = result.done
        named = result.text + " " + json.dumps(result.answer or {})
        rows.append(
            {
                "id": question["id"],
                "tools": [tool["name"] for tool in result.tools],
                "correct": all(dataset_id in named for dataset_id in question["expected_dataset_ids"]),
                "stop": done["stop"],
                "requests": done["requests"],
                "cost_usd": done["cost_usd"],
            }
        )

    with capsys.disabled():
        print()
        for row in rows:
            mark = "correct" if row["correct"] else "WRONG  "
            print(
                f"  {row['id']:5} {mark}  {row['requests']} requests  ${row['cost_usd']:.5f}"
                f"  tools: {', '.join(row['tools']) or 'none'}"
            )
        print(f"  total cost ${sum(row['cost_usd'] for row in rows):.4f}")

    assert all(row["stop"] == "final" for row in rows), "Each question must end with a final answer."
    assert all(row["tools"] for row in rows), (
        "The model answered a question without a tool. Tell it in the system prompt that it "
        "knows the catalogue only through the tools."
    )
    correct = sum(row["correct"] for row in rows)
    assert correct >= 4, (
        f"Only {correct} of 5 answers name each expected dataset id. Read the wrong answers: is "
        "the search tool missing the dataset, or does the answer not give the id?"
    )
