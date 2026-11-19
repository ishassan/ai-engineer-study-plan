"""Reference, state at the end of week 1: one request, no tools."""

from __future__ import annotations

from typing import Any, Iterator

from assistant.config import get_settings
from assistant.llm import stream_claude

SYSTEM_PROMPT = "You answer questions about a catalogue of public datasets. Be brief."


def answer_events(question: str) -> Iterator[tuple[str, dict[str, Any]]]:
    settings = get_settings()
    request = {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": question}],
    }
    for kind, value in stream_claude(request):
        if kind == "text":
            yield "text", {"text": value}
        else:
            result = value
    usage = result.message.usage
    yield "done", {
        "model": result.message.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        "requests": 1,
        "stop": "final",
    }
