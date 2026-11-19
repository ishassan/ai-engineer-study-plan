"""Reference solution."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterator

import anthropic
from anthropic.types import Message, Usage

from assistant.config import PRICES_PER_MTOK, get_settings


@dataclass
class ClaudeResult:
    message: Message
    cost_usd: float
    latency_ms: float
    replayed: bool


@lru_cache(maxsize=1)
def client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def cost_usd(model: str, usage: Usage) -> float:
    price = PRICES_PER_MTOK[model]
    return (
        usage.input_tokens * price["input"]
        + usage.output_tokens * price["output"]
        + (usage.cache_creation_input_tokens or 0) * price["cache_write_5m"]
        + (usage.cache_read_input_tokens or 0) * price["cache_read"]
    ) / 1_000_000


def _plain(value: Any) -> Any:
    return value.model_dump(mode="json", exclude_none=True)


def request_hash(request: dict[str, Any]) -> str:
    body = json.dumps(request, sort_keys=True, ensure_ascii=False, default=_plain)
    return hashlib.sha256(body.encode()).hexdigest()


def _log(result: ClaudeResult) -> None:
    settings = get_settings()
    message, usage = result.message, result.message.usage
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": message.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
        "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
        "replayed": result.replayed,
    }
    settings.request_log_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.request_log_path.open("a") as log:
        log.write(json.dumps(line) + "\n")


def stream_claude(request: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    settings = get_settings()
    path = settings.response_cache_dir / f"{request_hash(request)}.json"
    started = time.perf_counter()
    if settings.response_cache and path.exists():
        message = Message.model_validate_json(path.read_text())
        for block in message.content:
            if block.type == "text":
                yield "text", block.text
        replayed = True
    else:
        with client().messages.stream(**request) as stream:
            for text in stream.text_stream:
                yield "text", text
            message = stream.get_final_message()
        replayed = False
        if settings.response_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(message.model_dump_json(exclude_none=True))
    result = ClaudeResult(
        message=message,
        cost_usd=0.0 if replayed else cost_usd(message.model, message.usage),
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        replayed=replayed,
    )
    _log(result)
    yield "result", result


def call_claude(request: dict[str, Any]) -> ClaudeResult:
    for kind, value in stream_claude(request):
        if kind == "result":
            return value
    raise RuntimeError("stream_claude ended without a result")
