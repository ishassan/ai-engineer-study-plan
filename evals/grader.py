"""The grader model: a pass or fail judgement for one failure category. Week 10.

The grader reads one output of the assistant (a row of the result file of `make testset`)
and decides if it shows the failure of your largest category. Its rubric is the file
evals/rubric.md.

Run it on your 50 labelled outputs in the notebook
phases/phase-3-evaluation/notebooks/grader_agreement.ipynb.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from assistant.config import get_settings  # noqa: F401 (you will use it)
from assistant.llm import call_claude  # noqa: F401 (you will use it)

ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = ROOT / "evals" / "rubric.md"


class Verdict(BaseModel):
    """The structured output of the grader. Keep the field `passed`. You can add fields."""

    reasoning: str = Field(description="A short reason for the decision, with the words of the rubric.")
    passed: bool = Field(description="True when the output passes the rubric, False when it shows the failure.")


def grade(example: dict[str, Any]) -> Verdict:
    """Grade one output with Claude and return the verdict. Week 10, step 2.

    `example` is one row of the result file of `make testset`, with the keys question,
    answer, dataset_ids, citations, cited_passages and tools. Use the keys that your
    rubric needs.

    Send one request with call_claude():
    - the rubric (the text of RUBRIC_PATH) in the system prompt,
    - the parts of the example that the rubric needs in the user message,
    - the JSON schema of Verdict in output_config, as the agent does with Answer.

    Validate the text of the response with Verdict.model_validate_json().
    """
    raise NotImplementedError("Week 10, step 2")


def agreement_rates(labels: list[bool], verdicts: list[bool]) -> tuple[float, float]:
    """Return (true positive rate, true negative rate) of the grader. Week 10, step 3.

    Each item of `labels` is your label of one output, and the item at the same position of
    `verdicts` is the decision of the grader. True means "passed", False means "failed".

    A positive is a failure:
    - true positive rate: of the outputs that you labelled as failed, the share that the
      grader also failed,
    - true negative rate: of the outputs that you labelled as passed, the share that the
      grader also passed.

    Raise ValueError when the two lists have different lengths, or when the labels have no
    failure or no pass (then one of the rates has no meaning).
    """
    raise NotImplementedError("Week 10, step 3")
