"""The test runner. Week 3.

    uv run python -m evals.run --set quick
    uv run python -m evals.run --set all --no-cache

Arguments:
    --set quick|all   quick runs the questions with "quick": true. all runs the 30 questions.
    --no-cache        turn the response cache off for this run (set RESPONSE_CACHE=off
                      in os.environ before the first request).
    --out PATH        where to write the results. Default: evals/results/<time>-<set>.jsonl

For each question, run answer_events() and collect the "answer" and the "done"
events. Write one JSON line for each question:

    id, question, passed, expected_dataset_ids, dataset_ids,
    input_tokens, output_tokens, cost_usd, latency_ms

A question passes when the answer names each expected dataset id. Print one
line for each question, and a last line with the number of passed questions
and the total cost.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("Week 3, step 4")


if __name__ == "__main__":
    main()
