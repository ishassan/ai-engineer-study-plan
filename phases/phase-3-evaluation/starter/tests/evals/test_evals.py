"""The evaluation suite of CI. Week 11, step 2.

    make evals

This suite calls the real Claude API: `make evals` turns the fake API of the lab checks off
(`-p no:labkit.plugin`). Postgres with the chunks and both model services must run.

Write the suite in this file:

- Cases: the cases of evals/testset.jsonl with "ci": true, at most 15. The subset is fixed,
  so a change of score comes from a change of the code or the prompt, not of the cases.
- Run each case one time for the whole session, for example with a session-scoped fixture
  that calls run_case() from evals/run_testset.py.
- One score for each check, as a share of the cases (0.0 to 1.0):
  - the answer names each expected dataset ID (cases with expected_dataset_ids),
  - the citations are valid (each cited chunk exists, with its title and page), and the
    answer cites an expected chunk (cases with expected_chunk_ids),
  - your grader of week 10 passes the output.
- One test for each score, which fails when the score is below its threshold. Put the
  thresholds in constants at the top of this file, and print each score with its threshold.
"""

from __future__ import annotations


def test_the_suite_is_written():
    raise NotImplementedError("Week 11, step 2")
