"""A small local stand-in for the Claude Messages API, for the offline checks.

The checks start this server on localhost and set ANTHROPIC_BASE_URL to its
address. Your code then uses the real `anthropic` SDK, and the SDK talks to this
server in place of api.anthropic.com. No request leaves your machine and no
check costs money.

The server follows the documented rules of the real API for the parts that the
labs use:

- the response and streaming formats of POST /v1/messages,
- the pairing of `tool_use` and `tool_result` blocks (a wrong pairing gets a 400),
- prompt caching: a cache entry is written only at a `cache_control` breakpoint,
  a read looks back at most 20 blocks for an entry that an earlier request wrote,
  and a prefix below 512 tokens is not cached.

It does not run a model. A check tells the server which replies to give with
`fake.script(...)`. When the script is empty, the server sends a short text.
Token counts are estimates: one token for each four characters.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

MIN_CACHE_TOKENS = 512
LOOKBACK_BLOCKS = 20


@dataclass
class Reply:
    """One scripted reply of the model."""

    content: list[dict[str, Any]]
    stop_reason: str = "end_turn"
    usage: dict[str, int] | None = None
    status: int = 200
    error: dict[str, str] | None = None


def text_reply(
    text: str,
    *,
    thinking: bool = False,
    stop_reason: str = "end_turn",
    usage: dict[str, int] | None = None,
) -> Reply:
    """A final answer in plain text."""
    content: list[dict[str, Any]] = [_thinking_block()] if thinking else []
    content.append({"type": "text", "text": text})
    return Reply(content=content, stop_reason=stop_reason, usage=usage)


def json_reply(value: Any, **kwargs: Any) -> Reply:
    """A final answer whose text is a JSON document, as structured output gives."""
    return text_reply(json.dumps(value), **kwargs)


def answer_reply(
    text: str,
    *,
    dataset_ids: list[str] | None = None,
    tools_called: list[str] | None = None,
    usage: dict[str, int] | None = None,
) -> Callable[[dict[str, Any]], Reply]:
    """A final answer in the form that the request asks for.

    When the request has `output_config.format` (week 3 and later), the reply is
    the JSON document of the Answer model. Without it, the reply is plain text.
    """

    def build(body: dict[str, Any]) -> Reply:
        if wants_json(body):
            value = {
                "answer": text,
                "dataset_ids": dataset_ids or [],
                "tools_called": tools_called or [],
            }
            return json_reply(value, usage=usage)
        return text_reply(text, usage=usage)

    return build


def tool_reply(
    *calls: tuple[str, dict[str, Any]],
    text: str | None = None,
    thinking: bool = True,
    usage: dict[str, int] | None = None,
) -> Reply:
    """A reply that asks for one or more tools. Each call is (tool name, input)."""
    content: list[dict[str, Any]] = [_thinking_block()] if thinking else []
    if text:
        content.append({"type": "text", "text": text})
    for name, tool_input in calls:
        content.append(
            {"type": "tool_use", "id": _next_id("toolu_fake"), "name": name, "input": tool_input}
        )
    return Reply(content=content, stop_reason="tool_use", usage=usage)


def error_reply(status: int, error_type: str, message: str) -> Reply:
    """An API error, for example 529 overloaded_error."""
    return Reply(content=[], status=status, error={"type": error_type, "message": message})


_counter = 0
_counter_lock = threading.Lock()
_issued_signatures: set[str] = set()


def _next_id(prefix: str) -> str:
    global _counter
    with _counter_lock:
        _counter += 1
        return f"{prefix}_{_counter:04d}"


def _thinking_block() -> dict[str, Any]:
    # Haiku 5.5 returns thinking blocks with an empty text and a signature,
    # because the default display is "omitted".
    signature = _next_id("fake-signature")
    _issued_signatures.add(signature)
    return {"type": "thinking", "thinking": "", "signature": signature}


def _tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return max(1, len(text) // 4)


class RequestError(Exception):
    def __init__(self, message: str, status: int = 400, error_type: str = "invalid_request_error"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.error_type = error_type


@dataclass
class FakeClaude:
    """The state of the fake server: the script, the requests it got, the cache."""

    requests: list[dict[str, Any]] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    token_count_requests: list[dict[str, Any]] = field(default_factory=list)
    _script: deque[Reply | Callable[[dict[str, Any]], Reply]] = field(default_factory=deque)
    _default: Callable[[dict[str, Any]], Reply] | None = None
    _cache_entries: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    url: str = ""

    # ---- what a check calls -------------------------------------------------

    def reset(self) -> None:
        """Forget the script, the recorded requests and the prompt cache."""
        with self._lock:
            self.requests.clear()
            self.headers.clear()
            self.token_count_requests.clear()
            self._script.clear()
            self._default = None
            self._cache_entries.clear()

    def script(self, *replies: Reply | Callable[[dict[str, Any]], Reply]) -> None:
        """Queue replies. Each request takes the next one."""
        with self._lock:
            self._script.extend(replies)

    def always(self, reply: Reply | Callable[[dict[str, Any]], Reply]) -> None:
        """Give this reply to each request that the script does not cover."""
        with self._lock:
            self._default = reply if callable(reply) else (lambda _body: reply)

    @property
    def last_request(self) -> dict[str, Any]:
        assert self.requests, "Your code sent no request to the Claude API."
        return self.requests[-1]

    # ---- request handling ---------------------------------------------------

    def _next_reply(self, body: dict[str, Any]) -> Reply:
        with self._lock:
            item = self._script.popleft() if self._script else self._default
        if item is None:
            item = answer_reply(f"Fake answer to: {first_user_text(body)}")
        return item(body) if callable(item) else item

    def _usage(self, body: dict[str, Any], reply: Reply) -> dict[str, Any]:
        blocks = _prompt_blocks(body)
        total = sum(tokens for _, tokens, _ in blocks)
        read = written = 0
        breakpoints = [i for i, (_, _, marked) in enumerate(blocks) if marked]
        prefix_hashes = _prefix_hashes(blocks)
        prefix_tokens = _running_total([tokens for _, tokens, _ in blocks])
        with self._lock:
            for position in breakpoints:
                for candidate in range(position, max(-1, position - LOOKBACK_BLOCKS), -1):
                    if prefix_hashes[candidate] in self._cache_entries:
                        read = max(read, prefix_tokens[candidate])
                        break
            for position in breakpoints:
                if prefix_tokens[position] >= MIN_CACHE_TOKENS:
                    if prefix_hashes[position] not in self._cache_entries:
                        written = max(written, prefix_tokens[position] - read)
                    self._cache_entries.add(prefix_hashes[position])
        output = sum(_tokens(block) for block in reply.content) if reply.content else 1
        usage: dict[str, Any] = {
            "input_tokens": max(0, total - read - written),
            "output_tokens": output,
            "cache_creation_input_tokens": written,
            "cache_read_input_tokens": read,
        }
        if reply.usage is not None:
            # A check that scripts the usage gets exactly those numbers.
            usage.update(cache_creation_input_tokens=0, cache_read_input_tokens=0)
            usage.update(reply.usage)
        usage["cache_creation"] = {
            "ephemeral_5m_input_tokens": usage["cache_creation_input_tokens"],
            "ephemeral_1h_input_tokens": 0,
        }
        usage["service_tier"] = "standard"
        return usage

    async def _messages(self, request: Request) -> JSONResponse | StreamingResponse:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return _error(400, "invalid_request_error", "The request body is not valid JSON.")
        with self._lock:
            self.requests.append(body)
            self.headers.append(dict(request.headers))
        if not request.headers.get("x-api-key") and not request.headers.get("authorization"):
            return _error(401, "authentication_error", "x-api-key header is required")
        try:
            validate_request(body)
        except RequestError as error:
            return _error(error.status, error.error_type, error.message)
        reply = self._next_reply(body)
        if reply.error is not None:
            return _error(reply.status, reply.error["type"], reply.error["message"])
        message = {
            "id": _next_id("msg_fake"),
            "type": "message",
            "role": "assistant",
            "model": body["model"],
            "content": reply.content,
            "stop_reason": reply.stop_reason,
            "stop_sequence": None,
            "usage": self._usage(body, reply),
        }
        if body.get("stream"):
            return StreamingResponse(_sse_events(message), media_type="text/event-stream")
        return JSONResponse(message)

    async def _count_tokens(self, request: Request) -> JSONResponse:
        body = await request.json()
        with self._lock:
            self.token_count_requests.append(body)
        total = sum(tokens for _, tokens, _ in _prompt_blocks(body))
        return JSONResponse({"input_tokens": total})

    def app(self) -> Starlette:
        return Starlette(
            routes=[
                Route("/v1/messages", self._messages, methods=["POST"]),
                Route("/v1/messages/count_tokens", self._count_tokens, methods=["POST"]),
            ]
        )


# ---- helpers that checks also use ------------------------------------------


def last_user_text(body: dict[str, Any]) -> str:
    """The text of the last user message that is not a tool result."""
    for message in reversed(body.get("messages", [])):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        texts = [block.get("text", "") for block in content if block.get("type") == "text"]
        if texts:
            return " ".join(texts)
    return ""


def first_user_text(body: dict[str, Any]) -> str:
    """The text of the first user message: the question of the conversation."""
    for message in body.get("messages", []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            return " ".join(b.get("text", "") for b in content if b.get("type") == "text")
    return ""


def tool_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    """All tool_result blocks of the last message of a request."""
    content = body["messages"][-1].get("content")
    if isinstance(content, str):
        return []
    return [block for block in content if block.get("type") == "tool_result"]


def wants_json(body: dict[str, Any]) -> bool:
    """True when the request asks for structured output."""
    return bool((body.get("output_config") or {}).get("format"))


def has_cache_control(body: dict[str, Any]) -> bool:
    """True when the request asks for prompt caching anywhere."""
    return bool(body.get("cache_control")) or any(marked for _, _, marked in _prompt_blocks(body))


# ---- the rules of the real API that the fake also enforces ------------------


def validate_request(body: dict[str, Any]) -> None:
    for name in ("model", "max_tokens", "messages"):
        if name not in body:
            raise RequestError(f"{name}: Field required")
    messages = body["messages"]
    if not messages:
        raise RequestError("messages: at least one message is required")
    if messages[0].get("role") != "user":
        raise RequestError("messages: first message must use the user role")
    for index, tool in enumerate(body.get("tools") or []):
        if "name" not in tool:
            raise RequestError(f"tools.{index}.name: Field required")
        if "type" not in tool and "input_schema" not in tool:
            raise RequestError(f"tools.{index}.custom.input_schema: Field required")
        if "input_schema" in tool and tool["input_schema"].get("type") != "object":
            raise RequestError(f"tools.{index}.custom.input_schema.type: Input should be 'object'")

    for index, message in enumerate(messages):
        blocks = message.get("content")
        blocks = [] if isinstance(blocks, str) else blocks
        if message.get("role") == "assistant":
            for block in blocks:
                if block.get("type") == "thinking" and block.get("signature") not in _issued_signatures:
                    raise RequestError(
                        f"messages.{index}.content: Invalid `signature` in `thinking` block"
                    )
            wanted = [block["id"] for block in blocks if block.get("type") == "tool_use"]
            if not wanted:
                continue
            following = messages[index + 1] if index + 1 < len(messages) else None
            if following is None:
                continue  # The conversation can end on an assistant turn (prefill is not checked).
            next_blocks = following.get("content")
            next_blocks = [] if isinstance(next_blocks, str) else next_blocks
            given = [b.get("tool_use_id") for b in next_blocks if b.get("type") == "tool_result"]
            missing = [tool_id for tool_id in wanted if tool_id not in given]
            if following.get("role") != "user" or missing:
                raise RequestError(
                    f"messages.{index + 1}: `tool_use` ids were found without `tool_result` blocks "
                    f"immediately after: {', '.join(missing or wanted)}. Each `tool_use` block must "
                    "have a corresponding `tool_result` block in the next message."
                )
            seen_other = False
            for block in next_blocks:
                if block.get("type") == "tool_result":
                    if seen_other:
                        raise RequestError(
                            f"messages.{index + 1}: `tool_result` blocks must come first in the "
                            "content of the user message, before any text."
                        )
                else:
                    seen_other = True
        else:
            previous = messages[index - 1] if index > 0 else None
            previous_blocks = previous.get("content") if previous else []
            previous_blocks = [] if isinstance(previous_blocks, str) else previous_blocks
            known = {b["id"] for b in previous_blocks if b.get("type") == "tool_use"}
            for position, block in enumerate(blocks):
                if block.get("type") == "tool_result" and block.get("tool_use_id") not in known:
                    raise RequestError(
                        f"messages.{index}.content.{position}: unexpected `tool_use_id` found in "
                        f"`tool_result` blocks: {block.get('tool_use_id')}. Each `tool_result` block "
                        "must have a corresponding `tool_use` block in the previous message."
                    )


def _prompt_blocks(body: dict[str, Any]) -> list[tuple[str, int, bool]]:
    """The prompt as a flat list of (canonical text, tokens, has a cache breakpoint).

    The order is the order of the cache prefix: tools, then system, then messages.
    """
    blocks: list[tuple[str, int, bool]] = []

    def add(kind: str, value: Any) -> None:
        marked = isinstance(value, dict) and bool(value.get("cache_control"))
        if isinstance(value, dict):
            value = {key: item for key, item in value.items() if key != "cache_control"}
        text = kind + ":" + json.dumps(value, sort_keys=True)
        blocks.append((text, _tokens(text), marked))

    for tool in body.get("tools") or []:
        add("tool", tool)
    system = body.get("system")
    if isinstance(system, str):
        add("system", system)
    else:
        for block in system or []:
            add("system", block)
    for message in body.get("messages") or []:
        content = message.get("content")
        if isinstance(content, str):
            add(message.get("role", ""), content)
        else:
            for block in content or []:
                add(message.get("role", ""), block)
    if body.get("cache_control") and blocks:
        text, tokens, _ = blocks[-1]
        blocks[-1] = (text, tokens, True)  # Automatic caching marks the last block.
    return blocks


def _prefix_hashes(blocks: list[tuple[str, int, bool]]) -> list[str]:
    digest = hashlib.sha256()
    hashes = []
    for text, _, _ in blocks:
        digest.update(text.encode())
        hashes.append(digest.copy().hexdigest())
    return hashes


def _running_total(values: list[int]) -> list[int]:
    totals, total = [], 0
    for value in values:
        total += value
        totals.append(total)
    return totals


def _error(status: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"type": "error", "error": {"type": error_type, "message": message}}, status_code=status
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _sse_events(message: dict[str, Any]):
    """Yield the same event sequence that the real API streams for a message."""
    final_usage = message["usage"]
    start = dict(message, content=[], stop_reason=None)
    start["usage"] = dict(final_usage, output_tokens=1)
    yield _sse("message_start", {"type": "message_start", "message": start})
    yield _sse("ping", {"type": "ping"})
    for index, block in enumerate(message["content"]):
        if block["type"] == "text":
            opening = {"type": "text", "text": ""}
            deltas = [{"type": "text_delta", "text": part} for part in _chunks(block["text"], 12)]
        elif block["type"] == "tool_use":
            opening = dict(block, input={})
            partial = json.dumps(block["input"])
            deltas = [
                {"type": "input_json_delta", "partial_json": part} for part in _chunks(partial, 16)
            ]
        else:  # thinking
            opening = {"type": "thinking", "thinking": "", "signature": ""}
            deltas = [
                {"type": "thinking_delta", "thinking": ""},
                {"type": "signature_delta", "signature": block["signature"]},
            ]
        yield _sse(
            "content_block_start",
            {"type": "content_block_start", "index": index, "content_block": opening},
        )
        for delta in deltas:
            yield _sse(
                "content_block_delta",
                {"type": "content_block_delta", "index": index, "delta": delta},
            )
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": index})
    yield _sse(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None},
            "usage": final_usage,
        },
    )
    yield _sse("message_stop", {"type": "message_stop"})


# ---- running the server ------------------------------------------------------


class FakeClaudeServer:
    """Run a FakeClaude on a free localhost port, in a background thread."""

    def __init__(self) -> None:
        self.fake = FakeClaude()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.fake.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(self.fake.app(), host="127.0.0.1", port=self.port, log_level="error")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> FakeClaude:
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("The fake Claude API did not start.")
            time.sleep(0.02)
        return self.fake

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
