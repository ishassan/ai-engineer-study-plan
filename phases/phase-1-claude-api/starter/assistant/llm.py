"""The one place that calls Claude. Weeks 1 and 3.

Each request to Claude in this project goes through stream_claude(). The
function adds three things to a plain SDK call:

- it streams the text to the caller,
- it writes one line to the request log, with tokens, cost and latency,
- it keeps a response cache, so that a request you already sent costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from anthropic.types import Message, Usage

from assistant.config import PRICES_PER_MTOK, get_settings  # noqa: F401 (you will use them)


@dataclass
class ClaudeResult:
    """One complete response of Claude, and what it cost."""

    message: Message
    cost_usd: float  # 0.0 when the response came from the response cache
    latency_ms: float
    replayed: bool  # True when the response came from the response cache


def cost_usd(model: str, usage: Usage) -> float:
    """Return the price of one response in US dollars.

    Week 1: count input and output tokens with the prices in PRICES_PER_MTOK.
    Week 3: add the cache write and cache read tokens. They are in
    usage.cache_creation_input_tokens and usage.cache_read_input_tokens, and
    each can be None.
    """
    raise NotImplementedError("Week 1, step 4")


def request_hash(request: dict[str, Any]) -> str:
    """Return a hash of the full request body, as a hex string.

    Two requests with the same content must give the same hash, also when their
    keys are in a different order. From week 2, the messages hold SDK objects
    (the content blocks of a response), so the function must also accept those.
    """
    raise NotImplementedError("Week 1, step 5")


def stream_claude(request: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Send one request to Claude and yield what comes back.

    `request` holds the arguments of client.messages.stream(): model,
    max_tokens, system, messages, and later tools and output_config.

    Yield ("text", piece) for each piece of text when it arrives. At the end,
    yield ("result", ClaudeResult) one time.

    Rules:
    - Read the settings with get_settings() on each call.
    - Response cache on (settings.response_cache): if a file for the hash of
      this request exists in settings.response_cache_dir, do not call the API.
      Load the saved message, yield its text, and mark the result as replayed
      with a cost of 0. If no file exists, call the API and save the message.
    - Response cache off: always call the API, and save nothing.
    - Always append one JSON line to settings.request_log_path with at least:
      model, input_tokens, output_tokens, cache_creation_input_tokens,
      cache_read_input_tokens, cost_usd, latency_ms, replayed.
    """
    raise NotImplementedError("Week 1, steps 4 and 5")
    yield  # This line makes the function a generator. Remove it with the line above.


def call_claude(request: dict[str, Any]) -> ClaudeResult:
    """Send one request and return the result, for callers that do not stream."""
    for kind, value in stream_claude(request):
        if kind == "result":
            return value
    raise RuntimeError("stream_claude() ended without a result")
