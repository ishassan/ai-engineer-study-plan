"""Reference solution: the planner of week 13."""

from __future__ import annotations

from anthropic import transform_schema
from pydantic import BaseModel, Field

from assistant.config import get_settings
from assistant.llm import call_claude
from assistant.tools import TOOLS


class Plan(BaseModel):
    steps: list[str] = Field(description="The steps, in order. Each step is one short sentence.")


PLANNER_PROMPT = """\
You plan the work of the assistant of a data platform. Write the steps that answer the \
question of the user, in order, one short sentence each. A step names the tool that it uses. \
Write at most five steps. The last step writes the answer.

The tools:
{tools}\
"""

REPLAN = """\
The question: {question}

The current plan:
{plan}

A step failed. The tool {tool} with the input {tool_input} returned this error:
{error}

Write a new plan for the rest of the work. Do not repeat the step that failed in the same way.\
"""


def tool_list() -> str:
    return "\n".join(f"- {tool['name']}: {tool['description'].split('. ')[0]}." for tool in TOOLS)


def numbered(plan: Plan) -> str:
    return "\n".join(f"{n}. {step}" for n, step in enumerate(plan.steps, start=1))


def plan_request(text: str) -> dict:
    settings = get_settings()
    return {
        "model": settings.model,
        "max_tokens": 1024,
        "system": PLANNER_PROMPT.format(tools=tool_list()),
        "output_config": {"format": {"type": "json_schema", "schema": transform_schema(Plan)}},
        "messages": [{"role": "user", "content": text}],
    }


def _plan(request: dict):
    result = call_claude(request)
    text = "".join(block.text for block in result.message.content if block.type == "text")
    return Plan.model_validate_json(text), result


def write_plan(question: str):
    """The first plan for a question. Returns (plan, model result)."""
    return _plan(plan_request(question))


def change_plan(question: str, plan: Plan, tool: str, tool_input: dict, error: str):
    """A new plan after a failed step. Returns (plan, model result)."""
    text = REPLAN.format(question=question, plan=numbered(plan), tool=tool, tool_input=tool_input, error=error)
    return _plan(plan_request(text))
