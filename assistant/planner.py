"""The planner. Week 13.

With AGENT_PLANNER=on, the agent first asks the model for a plan (structured output with
the schema of Plan), sends the plan to the client as the event `plan`, and then works on
the steps of the plan. When a step fails (a tool returns an error), the agent asks the
model for a changed plan, sends the new plan as a second `plan` event, and goes on with it.

The class Plan is given: the checks send a plan in this form. You can add fields with a
default value. Change the signatures of the functions if your design needs other values
(for example, the model result, so the `done` event counts the cost of the plan).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Plan(BaseModel):
    steps: list[str] = Field(description="The steps, in order. Each step is one short sentence.")


def write_plan(question: str) -> Plan:
    """Ask the model for a plan for the question.

    Give the model the names of the tools and what each one does, so that each step can
    name a tool. Ask for the JSON schema of Plan (output_config.format, as the Answer of
    week 3). Use call_claude().
    """
    raise NotImplementedError("Week 13, step 2")


def change_plan(question: str, plan: Plan, tool: str, tool_input: dict, error: str) -> Plan:
    """Ask the model for a new plan after a step failed.

    Give the model the question, the current plan, the tool call that failed and its
    error message, so the new plan does not repeat the same step in the same way.
    """
    raise NotImplementedError("Week 13, step 2")
