"""Week 10 checks: the rubric, the grader, your 50 labels and the agreement rates.

Run them with `make check WEEK=10`. The grader checks use the fake Claude API of the lab, so
they are free. The last check prints the agreement rates that your notebook measured.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from labkit.fake_claude import json_reply

REPO = Path(__file__).resolve().parents[3]
RUBRIC = REPO / "evals" / "rubric.md"
LABELS = REPO / "evals" / "grader_labels.jsonl"
AGREEMENT = REPO / "evals" / "grader_agreement.json"
STARTER_LINE = "Write the rubric here (week 10, step 2)."

EXAMPLE = {
    "id": "check-1",
    "question": "Which dataset has the crude oil production of Saudi Arabia?",
    "answer": "The dataset Crude Oil Production has it. (check answer 7f3a)",
    "dataset_ids": ["saudi-crude-oil-production-from-sama-annual-statistics-2015-dec"],
    "citations": [],
    "cited_passages": [],
    "tools": [{"name": "search_datasets", "input": {"query": "crude oil production"}, "is_error": False}],
    "errors": [],
}


def verdict_reply(passed: bool):
    """A reply in the schema that the request asks for, with `passed` set."""

    def build(body: dict[str, Any]):
        schema = ((body.get("output_config") or {}).get("format") or {}).get("schema") or {}
        value: dict[str, Any] = {}
        for name, field in (schema.get("properties") or {}).items():
            kind = field.get("type")
            if name == "passed":
                value[name] = passed
            elif kind == "boolean":
                value[name] = passed
            elif kind in ("integer", "number"):
                value[name] = 1
            elif kind == "array":
                value[name] = []
            else:
                value[name] = "The rubric decides."
        return json_reply(value or {"passed": passed}, usage={"input_tokens": 800, "output_tokens": 40})

    return build


def strings(value: Any) -> list[str]:
    """Each string in a request body, also inside JSON text that the code put in a message."""
    if isinstance(value, str):
        try:
            inner = json.loads(value[value.index("{") :]) if "{" in value else None
        except json.JSONDecodeError:
            inner = None
        return [value] + (strings(inner) if inner is not None else [])
    if isinstance(value, dict):
        return [s for item in value.values() for s in strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in strings(item)]
    return []


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- step 3: the agreement rates (the function first, because the notebook uses it) ----------


@pytest.mark.parametrize(
    "labels, verdicts, rates",
    [
        ([True, True, False, False], [True, True, False, False], (1.0, 1.0)),
        ([False, False, False, False, True], [False, False, False, True, True], (0.75, 1.0)),
        ([True, True, True, True, False, False], [True, False, True, False, False, True], (0.5, 0.5)),
        ([False, True, True, True, True], [True, True, True, True, False], (0.0, 0.75)),
    ],
)
def test_agreement_rates_count_a_failure_as_the_positive_class(labels, verdicts, rates):
    from evals.grader import agreement_rates

    result = agreement_rates(labels, verdicts)
    assert tuple(result) == pytest.approx(rates), (
        f"agreement_rates({labels}, {verdicts}) must give {rates}: (true positive rate, true negative rate). "
        "A positive is a failure: the true positive rate is the share of your failures that the grader also fails."
    )


@pytest.mark.parametrize(
    "labels, verdicts",
    [([True, False, True], [True, False]), ([True, True, True], [True, False, True]), ([False, False], [False, True])],
    ids=["different lengths", "no failure in the labels", "no pass in the labels"],
)
def test_agreement_rates_reject_labels_that_give_no_rate(labels, verdicts):
    from evals.grader import agreement_rates

    with pytest.raises(ValueError):
        agreement_rates(labels, verdicts)


# ---- step 2: the rubric and the grader -----------------------------------------------------


def test_the_rubric_is_written():
    assert RUBRIC.exists(), "evals/rubric.md does not exist. Run `make start PHASE=3`."
    text = RUBRIC.read_text(encoding="utf-8")
    assert STARTER_LINE not in text, "Write the rubric in evals/rubric.md, and delete the first line of the template."
    lower = text.lower()
    assert len(text) >= 600 and "pass" in lower and "fail" in lower and "example" in lower, (
        "The rubric needs the rule for a pass, the rule for a fail, and examples of both from your traces."
    )


def test_the_grader_sends_the_rubric_and_the_output_with_a_schema(fake, request_log):
    from evals.grader import grade

    fake.script(verdict_reply(True))
    grade(dict(EXAMPLE))
    assert len(fake.requests) == 1, "The grader sends one request for one output."
    body = fake.last_request
    text = " ".join(" ".join(strings(body)).split())
    rubric = " ".join(RUBRIC.read_text(encoding="utf-8").split())
    assert rubric[:300] in text, "Send the text of evals/rubric.md in the request."
    assert "check answer 7f3a" in text, "Send the answer of the output in the request."
    schema = ((body.get("output_config") or {}).get("format") or {}).get("schema") or {}
    assert (schema.get("properties") or {}).get("passed", {}).get("type") == "boolean", (
        "Send the JSON schema of Verdict in output_config, as the agent does with Answer."
    )
    assert len(request_log()) == 1, "Call Claude through call_claude(), so the request log has the call and its cost."


@pytest.mark.parametrize("passed", [True, False])
def test_the_grader_returns_the_decision_of_the_model(fake, passed):
    from evals.grader import grade

    fake.script(verdict_reply(passed))
    verdict = grade(dict(EXAMPLE))
    assert verdict.passed is passed, f"The model answered passed={passed}, and grade() returned {verdict.passed}."


# ---- step 3: your labels and the measured rates ----------------------------------------------


def test_you_labelled_50_outputs():
    assert LABELS.exists(), "evals/grader_labels.jsonl does not exist. Label 50 outputs in the notebook (part 1)."
    labels = read_jsonl(LABELS)
    ids = [item.get("id") for item in labels]
    assert len(set(ids)) == len(ids), "Keep one label for each output."
    assert len(labels) >= 50, f"You labelled {len(labels)} outputs. Label 50."
    values = [item.get("label") for item in labels]
    assert set(values) <= {"pass", "fail"}, "Each label is 'pass' or 'fail'."
    assert values.count("pass") >= 10 and values.count("fail") >= 10, (
        f"{values.count('pass')} passes and {values.count('fail')} failures. Each rate needs at least 10 "
        "outputs of its class, or one disagreement moves it by more than 10 points."
    )
    for item in labels:
        assert item.get("question") and "answer" in item, f"{item['id']}: keep the output with its label."


def test_the_agreement_rates_are_measured_on_your_labels(capsys):
    from evals.grader import agreement_rates

    assert AGREEMENT.exists(), "evals/grader_agreement.json does not exist. Run part 2 and part 3 of the notebook."
    result = json.loads(AGREEMENT.read_text(encoding="utf-8"))
    labels = {item["id"]: item["label"] for item in read_jsonl(LABELS)}
    rows = {row["id"]: row for row in result["rows"]}
    assert set(rows) == set(labels), "Run the grader on each labelled output, and on no other."
    changed = [i for i in labels if rows[i]["label"] != labels[i]]
    assert not changed, f"These labels changed after the grader ran: {changed}. Run part 2 and part 3 again."
    ordered = sorted(labels)
    tpr, tnr = agreement_rates(
        [labels[i] == "pass" for i in ordered], [rows[i]["grader"] == "pass" for i in ordered]
    )
    assert (result["true_positive_rate"], result["true_negative_rate"]) == pytest.approx((tpr, tnr))
    rubric = RUBRIC.read_text(encoding="utf-8")
    assert result.get("rubric") == rubric, "The rubric changed after the last run of the grader. Run part 2 and part 3 again."
    with capsys.disabled():
        print(f"\n  The grader agrees with your {len(labels)} labels: true positive rate {tpr:.2f}, true negative rate {tnr:.2f}.")
        print("  Write both rates in phases/phase-3-evaluation/RESULTS.md.")
