"""Reference, state at the end of week 2: the loop with tools, plain text answer."""

from __future__ import annotations

from typing import Any, Iterator

from assistant.config import get_settings
from assistant.llm import stream_claude
from assistant.tools import TOOLS, run_tool

SYSTEM_PROMPT = (
    "You answer questions about a catalogue of public datasets. Use the tools to find "
    "datasets. Name the id of each dataset that you use. Be brief."
)


def answer_events(question: str) -> Iterator[tuple[str, dict[str, Any]]]:
    settings = get_settings()
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    totals = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_ms": 0.0}
    requests = 0
    stop = "max_turns"
    model = settings.model
    for _ in range(settings.max_turns):
        request = {
            "model": settings.model,
            "max_tokens": settings.max_tokens,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "messages": messages,
        }
        for kind, value in stream_claude(request):
            if kind == "text":
                yield "text", {"text": value}
            else:
                result = value
        message = result.message
        requests += 1
        model = message.model
        totals["input_tokens"] += message.usage.input_tokens
        totals["output_tokens"] += message.usage.output_tokens
        totals["cost_usd"] += result.cost_usd
        totals["latency_ms"] += result.latency_ms
        if message.stop_reason != "tool_use":
            stop = "final"
            break
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
    if stop == "max_turns":
        yield "error", {"message": f"No final answer after {settings.max_turns} turns."}
    yield "done", {"model": model, **totals, "requests": requests, "stop": stop}
