"""Reference solution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anthropic import transform_schema
from pydantic import BaseModel, Field

from assistant.config import get_settings
from assistant.llm import call_claude

ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = ROOT / "evals" / "rubric.md"


class Verdict(BaseModel):
    """The structured output of the grader. Keep the field `passed`. You can add fields."""

    reasoning: str = Field(description="A short reason for the decision, with the words of the rubric.")
    passed: bool = Field(description="True when the output passes the rubric, False when it shows the failure.")


def grade(example: dict[str, Any]) -> Verdict:
    settings = get_settings()
    shown = {
        "question": example.get("question"),
        "tool_calls": [{"name": t.get("name"), "input": t.get("input")} for t in example.get("tools", [])],
        "answer": example.get("answer"),
        "dataset_ids": example.get("dataset_ids", []),
        "citations": example.get("citations", []),
    }
    request = {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": [{"type": "text", "text": RUBRIC_PATH.read_text(encoding="utf-8")}],
        "messages": [
            {
                "role": "user",
                "content": "Grade this output of the assistant with the rubric.\n\n"
                + json.dumps(shown, ensure_ascii=False, indent=1),
            }
        ],
        "output_config": {"format": {"type": "json_schema", "schema": transform_schema(Verdict)}},
    }
    result = call_claude(request)
    text = "".join(block.text for block in result.message.content if block.type == "text")
    return Verdict.model_validate_json(text)


def agreement_rates(labels: list[bool], verdicts: list[bool]) -> tuple[float, float]:
    if len(labels) != len(verdicts):
        raise ValueError(f"{len(labels)} labels and {len(verdicts)} verdicts")
    failed = [verdict for label, verdict in zip(labels, verdicts) if not label]
    passed = [verdict for label, verdict in zip(labels, verdicts) if label]
    if not failed or not passed:
        raise ValueError("The labels need at least one failure and one pass.")
    true_positive_rate = sum(not verdict for verdict in failed) / len(failed)
    true_negative_rate = sum(verdict for verdict in passed) / len(passed)
    return true_positive_rate, true_negative_rate
