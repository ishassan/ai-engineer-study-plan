"""Week 13 checks: the planner, by hand.

Run them with `make check WEEK=13`. They use the fake Claude API on localhost, so they are
free. Postgres must run (`make up`). The checks use the hand-written loop
(AGENT_IMPL=handwritten) with AGENT_PLANNER=on.

The fake API plays the model: it gives a plan, asks for a tool call that fails, gives a
changed plan when your loop asks for one, and then answers.
"""

from __future__ import annotations

from typing import Any

import pytest
from phase4_helpers import answer_value, asks_for_plan, prompt_text, structured

from labkit.fake_claude import Reply, tool_reply
from labkit.sse import ask

QUESTION = "Which columns does the dataset of crude oil production have?"
BAD_ID = "crude-oil-production-check-unknown"
PLAN_1 = [
    f"Get the schema of the dataset {BAD_ID} with get_dataset_schema.",
    "Write the answer with the columns.",
]
PLAN_2 = [
    "Search the catalogue for crude oil production with search_datasets.",
    "Get the schema of the best dataset with get_dataset_schema.",
    "Write the answer with the columns.",
]


@pytest.fixture(autouse=True)
def planner_on(monkeypatch):
    monkeypatch.setenv("AGENT_IMPL", "handwritten")
    monkeypatch.setenv("AGENT_PLANNER", "on")


class Model:
    """The fake model of a task with a failing step. It answers each request by its kind."""

    def __init__(self, provider: str = "anthropic", fail: bool = True) -> None:
        self.provider = provider
        self.fail = fail
        self.plans = 0
        self.failed = False
        self.searched = False
        self.kinds: list[str] = []

    def __call__(self, body: dict[str, Any]) -> Reply:
        if asks_for_plan(body):
            self.plans += 1
            self.kinds.append(f"plan{self.plans}")
            steps = PLAN_1 if self.plans == 1 else PLAN_2
            return structured(self.provider, {"steps": steps})(body)
        self.kinds.append("agent")
        if self.plans == 1 and self.fail and not self.failed:
            self.failed = True
            return self.tool(("get_dataset_schema", {"dataset_id": BAD_ID}))
        if (self.plans >= 2 or not self.fail) and not self.searched:
            self.searched = True
            return self.tool(("search_datasets", {"query": "crude oil production"}))
        return self.answer(body)

    def tool(self, *calls):
        if self.provider == "openai":
            from labkit.fake_openai import tool_reply as openai_tool_reply

            return openai_tool_reply(*calls)
        return tool_reply(*calls)

    def answer(self, body):
        text = "The dataset has the columns year, region and volume."
        return structured(self.provider, lambda request: answer_value(request, text))(body)


def test_without_the_planner_there_is_no_plan(client, fake, monkeypatch):
    monkeypatch.setenv("AGENT_PLANNER", "off")
    model = Model()
    fake.always(model)
    result = ask(client, QUESTION)

    assert model.plans == 0 and result.of("plan") == [], "With AGENT_PLANNER=off the loop works as in Phase 3."
    assert result.answer is not None


def test_the_plan_comes_first_and_is_sent_as_an_event(client, fake):
    model = Model(fail=False)
    fake.always(model)
    result = ask(client, QUESTION)

    assert model.kinds[:1] == ["plan1"], (
        "The first request asks for the plan: structured output with the schema of Plan (a field "
        f"`steps`). Requests: {model.kinds}"
    )
    plan_request = fake.requests[0]
    assert QUESTION in prompt_text(plan_request), "The plan request must hold the question."
    for name in ("search_datasets", "get_dataset_schema", "search_documents"):
        assert name in prompt_text(plan_request) or name in str(plan_request.get("tools")), (
            f"The plan request must name the tools, so that each step can use one. Missing: {name}"
        )
    plans = result.of("plan")
    assert [plan["steps"] for plan in plans] == [PLAN_1], "Send the plan as the event `plan` with its `steps`."
    assert result.names.index("plan") < result.names.index("tool"), "The plan comes before the first tool call."
    assert any(PLAN_1[0] in prompt_text(body) for body in fake.requests[1:]), "Give the plan to the model."
    assert result.answer is not None and result.names[-2:] == ["answer", "done"]
    assert model.plans == 1, "No step failed, so the plan does not change."


def test_a_failed_step_changes_the_plan_and_the_task_finishes(client, fake):
    model = Model()
    fake.always(model)
    result = ask(client, QUESTION)

    assert result.tools and result.tools[0]["name"] == "get_dataset_schema" and result.tools[0]["is_error"], (
        f"The first step calls get_dataset_schema with an unknown ID, and the tool fails. Tools: {result.tools}"
    )
    assert model.plans == 2, (
        "A step failed, so ask the model for a new plan before the next model call of the loop. "
        f"Requests: {model.kinds}"
    )
    replan = next(body for body in fake.requests if asks_for_plan(body) and body is not fake.requests[0])
    text = prompt_text(replan)
    assert BAD_ID in text, "The request for the new plan must name the step that failed."
    assert "No dataset has the id" in text or "LookupError" in text, "The request for the new plan must hold the error."
    plans = [plan["steps"] for plan in result.of("plan")]
    assert plans == [PLAN_1, PLAN_2], "Send each plan as a `plan` event: the first one and the changed one."
    names = [name for name in result.names if name in {"plan", "tool", "answer", "done"}]
    assert names == ["plan", "tool", "plan", "tool", "answer", "done"], names
    after = fake.requests[model.kinds.index("plan2") + 1]
    assert PLAN_2[0] in prompt_text(after), "The model must get the new plan in the next request."
    assert result.answer is not None and result.done["stop"] == "final"
    assert result.done["requests"] == len(fake.requests), (
        "The `done` event counts each model request, also the two plan requests, and adds their cost."
    )
