"""Week 24: the training data of the LoRA fine-tune.

The checks read your data/train.jsonl. One line is one example in the conversational format of
the TRL SFT trainer: {"messages": [{"role": ..., "content": ...}, ...]}. The roles are system
(optional, first), user and assistant, and the last message is the answer of the assistant.

Two texts are the same when they are the same after normalise_arabic() of Phase 2 (no
diacritics, no tatweel), with the spaces collapsed, the end punctuation removed, and the case
ignored.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

import pytest

from phase6_helpers import REPO, TESTSET, read_jsonl

TRAIN = REPO / "data" / "train.jsonl"
MINIMUM = 200
ROLES = {"system", "user", "assistant"}
ARABIC = re.compile(r"[؀-ۿ]")


def same_form(text: str) -> str:
    from assistant.ingest import normalise_arabic

    return " ".join(normalise_arabic(text).split()).strip(" ?؟.!،").casefold()


@pytest.fixture(scope="module")
def examples() -> list[Any]:
    """The examples of data/train.jsonl, None for a line that is not JSON. Each check calls require()."""
    if not TRAIN.exists():
        return []
    rows: list[Any] = []
    for line in TRAIN.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append(None)
    return rows


def require(examples: list[Any]) -> None:
    assert TRAIN.exists(), "data/train.jsonl does not exist. Write your training set there (step 3)."
    assert examples and all(isinstance(example, dict) for example in examples), (
        "Each line of data/train.jsonl must be one JSON object."
    )


def user_text(example: dict[str, Any]) -> str:
    return "\n".join(m["content"] for m in example["messages"] if m["role"] == "user")


def test_each_example_is_in_the_chat_format_of_trl(examples):
    require(examples)
    problems = []
    for number, example in enumerate(examples, start=1):
        messages = example.get("messages") if isinstance(example, dict) else None
        if not isinstance(messages, list) or len(messages) < 2:
            problems.append(f"example {number}: no list `messages` with a question and an answer")
            continue
        roles = [m.get("role") if isinstance(m, dict) else None for m in messages]
        if set(roles) - ROLES or "system" in roles[1:]:
            problems.append(f"example {number}: the roles {roles} are not system (first only), user and assistant")
        elif "user" not in roles or roles[-1] != "assistant":
            problems.append(f"example {number}: it needs a user message, and the last message must be the assistant's")
        elif not all(isinstance(m.get("content"), str) and m["content"].strip() for m in messages):
            problems.append(f"example {number}: each message needs a text in `content`")
    assert not problems, f"data/train.jsonl is not in the format of the SFT trainer: {problems[:10]}"


def test_the_training_set_has_a_few_hundred_examples(examples):
    require(examples)
    assert len(examples) >= MINIMUM, (
        f"data/train.jsonl has {len(examples)} examples. The plan asks for a few hundred: at least {MINIMUM} (step 3)."
    )


def test_the_task_is_an_arabic_task(examples):
    require(examples)
    arabic = sum(bool(ARABIC.search(example["messages"][-1]["content"])) for example in examples)
    assert arabic >= 0.8 * len(examples), (
        f"Only {arabic} of {len(examples)} answers are in Arabic. Choose one Arabic task where the open model "
        "fails (step 2)."
    )


def test_no_example_is_a_duplicate(examples):
    require(examples)
    questions = Counter(same_form(user_text(example)) for example in examples)
    duplicates = [question for question, count in questions.items() if count > 1]
    assert not duplicates, (
        f"{len(duplicates)} questions are in the training set more than once, for example {duplicates[:3]}. "
        "Remove the duplicates (step 3)."
    )


def test_no_test_case_is_in_the_training_set(examples):
    require(examples)
    tests = {case["id"]: same_form(case["question"]) for case in read_jsonl(TESTSET)}
    leaked = sorted({case_id for example in examples for case_id, question in tests.items()
                     if question and question in same_form(user_text(example))})
    assert not leaked, (
        f"The questions of these test cases are in the training set: {leaked[:10]}. A model that trains on "
        "a test case gets a score that you cannot trust. Remove them (step 3)."
    )
