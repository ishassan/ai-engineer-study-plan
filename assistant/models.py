"""Reference solution: the chat models of the two providers."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage

from assistant.config import PRICES_PER_MTOK, get_settings
from assistant.llm import user_header

# The anthropic SDK makes its own OpenTelemetry span for each call when a tracer is registered
# (Langfuse registers one). The Langfuse callback of the graph already makes the generation, so
# the SDK span would count each call twice. ChatAnthropic makes its client itself, so the
# environment variable of the SDK turns the span off.
os.environ.setdefault("ANTHROPIC_OPEN_TELEMETRY", "false")


def chat_model(provider: str | None = None, user: str | None = None) -> BaseChatModel:
    """The chat model of the provider. With a gateway (Phase 6), each call goes to the gateway.

    `user` goes to the gateway in the header of the end user, so that the gateway counts the
    spend of each user against the budget of the user.
    """
    settings = get_settings()
    provider = provider or settings.provider
    gateway: dict[str, Any] = {}
    if settings.gateway_url:
        gateway = {"api_key": settings.gateway_key, "default_headers": user_header(user)}
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if gateway:
            gateway["base_url"] = f"{settings.gateway_url}/v1"
        # stream_usage: LangChain turns the usage of a stream off when OPENAI_BASE_URL is set.
        return ChatOpenAI(model=settings.openai_model, max_tokens=settings.max_tokens, stream_usage=True, **gateway)
    from langchain_anthropic import ChatAnthropic

    if gateway:
        gateway["base_url"] = settings.gateway_url
    return ChatAnthropic(model=settings.model, max_tokens=settings.max_tokens, **gateway)


def system_message(texts: list[str], provider: str | None = None) -> SystemMessage:
    """The system prompt. On Claude the first block is a cache breakpoint."""
    provider = provider or get_settings().provider
    if provider == "openai":
        return SystemMessage(content="\n\n".join(texts))
    blocks: list[str | dict[str, Any]] = [{"type": "text", "text": texts[0], "cache_control": {"type": "ephemeral"}}]
    blocks += [{"type": "text", "text": text} for text in texts[1:]]
    return SystemMessage(content=blocks)


def usage_of(message: AIMessage) -> dict[str, Any]:
    """The usage of one model call, in the fields of the `done` event, with its cost."""
    usage = message.usage_metadata or {}
    details = usage.get("input_token_details") or {}
    read = details.get("cache_read") or 0
    written = details.get("cache_creation") or 0
    model = message.response_metadata.get("model_name") or message.response_metadata.get("model") or ""
    numbers = {
        "input_tokens": max(0, usage.get("input_tokens", 0) - read - written),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_creation_input_tokens": written,
        "cache_read_input_tokens": read,
    }
    price = PRICES_PER_MTOK.get(model)
    if price is None:
        cost = 0.0
    else:
        cost = (
            numbers["input_tokens"] * price["input"]
            + numbers["output_tokens"] * price["output"]
            + written * price["cache_write_5m"]
            + read * price["cache_read"]
        ) / 1_000_000
    return {"model": model, **numbers, "cost_usd": cost}
