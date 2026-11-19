"""Reference, state at the end of week 3: typed answer and prompt caching."""

from __future__ import annotations

from typing import Any, Iterator

from anthropic import transform_schema
from pydantic import ValidationError

from assistant.config import get_settings
from assistant.llm import stream_claude
from assistant.schemas import Answer
from assistant.tools import TOOLS, run_tool

SYSTEM_PROMPT = """\
You are the assistant of a data platform. You answer questions about the datasets in its \
catalogue. The catalogue holds public datasets about Saudi Arabia from these owners: the \
General Authority for Statistics, the Saudi Central Bank (SAMA), the Electricity and \
Cogeneration Regulatory Authority, the Transport General Authority, the Ministry of \
Environment, Water and Agriculture, Saudi Open Data, and the King Abdullah Petroleum Studies \
and Research Center. The themes of the catalogue are: Buildings, Climate & Sustainability, \
Conventional Fuels, Economy, Electricity, Industry, Renewable & Other Fuels, Transport, and \
Water & Agriculture.

How to work:
- You know nothing about the catalogue except what the tools return. Always search before you \
answer, also when you think that you know the answer.
- Search with a few keywords. If a search returns nothing useful, search again with other \
words: a synonym, a wider term, or the name of the owner. Make at most four searches for one \
question.
- When the question is about the content of a dataset (its fields, its columns, what it \
measures), get the schema of the dataset before you answer.
- When the question is about the size, the last update, the update frequency, the license or \
the owner of a dataset, get the stats of the dataset before you answer.
- When several datasets fit the question, name each of them. Do not choose only one.
- When a tool returns an error, read the message, correct the input and try again one time.
- When no dataset fits the question, say that the catalogue has no dataset for it. Do not \
invent a dataset, an id, a column or a number.

How to answer:
- Give a short answer in plain text: two to four sentences. Name each dataset by its title.
- In dataset_ids, list the id of each dataset that the answer uses. Copy each id exactly as \
the tool returned it. List only datasets that answer the question, and not each search result.
- In tools_called, list the name of each tool that you called, one time each.
- Answer in the language of the question.
"""


def build_request(messages: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    return {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "tools": TOOLS,
        "system": [
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
        ],
        "output_config": {"format": {"type": "json_schema", "schema": transform_schema(Answer)}},
        "messages": messages,
    }


def answer_events(question: str) -> Iterator[tuple[str, dict[str, Any]]]:
    settings = get_settings()
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_usd": 0.0,
        "latency_ms": 0.0,
    }
    requests = 0
    stop = "max_turns"
    model = settings.model
    for _ in range(settings.max_turns):
        text = ""
        for kind, value in stream_claude(build_request(messages)):
            if kind == "text":
                text += value
            else:
                result = value
        message = result.message
        requests += 1
        model = message.model
        usage = message.usage
        totals["input_tokens"] += usage.input_tokens
        totals["output_tokens"] += usage.output_tokens
        totals["cache_creation_input_tokens"] += usage.cache_creation_input_tokens or 0
        totals["cache_read_input_tokens"] += usage.cache_read_input_tokens or 0
        totals["cost_usd"] += result.cost_usd
        totals["latency_ms"] += result.latency_ms
        if message.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": message.content})
            results = []
            for block in message.content:
                if block.type != "tool_use":
                    continue
                try:
                    output, is_error = run_tool(block.name, block.input), False
                except Exception as error:
                    output, is_error = f"{type(error).__name__}: {error}", True
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                        "is_error": is_error,
                    }
                )
                yield "tool", {"name": block.name, "input": block.input, "is_error": is_error}
            messages.append({"role": "user", "content": results})
            continue
        stop = "final"
        if message.stop_reason != "end_turn":
            yield "error", {"message": f"The model stopped with {message.stop_reason}."}
            break
        try:
            answer = Answer.model_validate_json(text)
        except ValidationError as error:
            yield "error", {"message": f"The answer is not valid: {error.errors()[0]['msg']}"}
            break
        yield "answer", answer.model_dump()
        break
    if stop == "max_turns":
        yield "error", {"message": f"No final answer after {settings.max_turns} turns."}
    yield "done", {"model": model, **totals, "requests": requests, "stop": stop}
