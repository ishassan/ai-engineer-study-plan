"""A small local stand-in for the OpenAI API, for the offline checks of Phase 4.

The checks start this server on localhost and set OPENAI_BASE_URL to its address.
Your code then uses the real `openai` SDK (through `langchain-openai`), and the SDK
talks to this server in place of api.openai.com. No request leaves your machine and
no check costs money.

`langchain-openai` uses two endpoints, so the server has both:

- POST /v1/responses, the Responses API. `ChatOpenAI` uses it for a model whose name
  starts with "gpt-6" when the request has tools, and when you set
  `use_responses_api=True`.
- POST /v1/chat/completions, the Chat Completions API. `ChatOpenAI` uses it in the
  other cases, for example for a request without tools.

For both endpoints the server gives the response and the streaming formats that the
`openai` SDK reads, with text, function calls, structured output (a JSON text) and
token usage. It also refuses a request that the real API refuses: a function call
whose result is missing, or a tool result whose call ID is unknown (400).

It does not run a model. A check tells the server which replies to give with
`fake.script(...)`, in the same way as `labkit.fake_claude`. When the script is empty,
the server sends a short text. Token counts are estimates: one token for each four
characters.

Phase 6: the server also stands in for vLLM on a rented GPU. `fake.delay` makes each reply
wait that many seconds before it starts, and `fake.max_in_flight` is the largest number of
requests that waited at the same time, so a check can see the load of a load test.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route


@dataclass
class Reply:
    """One scripted reply of the model."""

    text: str | None = None
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    usage: dict[str, int] | None = None
    status: int = 200
    error: dict[str, str] | None = None


def text_reply(text: str, *, usage: dict[str, int] | None = None) -> Reply:
    """A final answer in plain text."""
    return Reply(text=text, usage=usage)


def json_reply(value: Any, *, usage: dict[str, int] | None = None) -> Reply:
    """A final answer whose text is a JSON document, as structured output gives."""
    return Reply(text=json.dumps(value), usage=usage)


def tool_reply(
    *calls: tuple[str, dict[str, Any]], text: str | None = None, usage: dict[str, int] | None = None
) -> Reply:
    """A reply that asks for one or more function calls. Each call is (name, arguments)."""
    return Reply(text=text, tool_calls=list(calls), usage=usage)


def error_reply(status: int, error_type: str, message: str) -> Reply:
    """An API error, for example 429 rate_limit_exceeded."""
    return Reply(status=status, error={"type": error_type, "message": message})


def answer_reply(
    text: str,
    *,
    dataset_ids: list[str] | None = None,
    tools_called: list[str] | None = None,
    usage: dict[str, int] | None = None,
) -> Callable[[dict[str, Any]], Reply]:
    """A final answer in the form that the request asks for: JSON with a schema, else text."""

    def build(body: dict[str, Any]) -> Reply:
        if wants_json(body):
            value = {"answer": text, "dataset_ids": dataset_ids or [], "tools_called": tools_called or []}
            return json_reply(value, usage=usage)
        return text_reply(text, usage=usage)

    return build


_counter = 0
_counter_lock = threading.Lock()


def _next_id(prefix: str) -> str:
    global _counter
    with _counter_lock:
        _counter += 1
        return f"{prefix}_fake{_counter:04d}"


def _tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return max(1, len(text) // 4)


class RequestError(Exception):
    def __init__(self, message: str, param: str | None = None):
        super().__init__(message)
        self.message = message
        self.param = param


@dataclass
class FakeOpenAI:
    """The state of the fake server: the script and the requests it got."""

    requests: list[dict[str, Any]] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    _script: deque[Reply | Callable[[dict[str, Any]], Reply]] = field(default_factory=deque)
    _default: Callable[[dict[str, Any]], Reply] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    url: str = ""
    delay: float = 0.0
    in_flight: int = 0
    max_in_flight: int = 0

    # ---- what a check calls -------------------------------------------------

    def reset(self) -> None:
        """Forget the script and the recorded requests."""
        with self._lock:
            self.requests.clear()
            self.paths.clear()
            self.headers.clear()
            self._script.clear()
            self._default = None
            self.delay = 0.0
            self.in_flight = 0
            self.max_in_flight = 0

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
        assert self.requests, "Your code sent no request to the OpenAI API."
        return self.requests[-1]

    # ---- request handling ---------------------------------------------------

    def _next_reply(self, body: dict[str, Any]) -> Reply:
        with self._lock:
            item = self._script.popleft() if self._script else self._default
        if item is None:
            item = answer_reply(f"Fake answer to: {first_user_text(body)}")
        return item(body) if callable(item) else item

    async def _receive(self, request: Request, validate: Callable[[dict[str, Any]], None]):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return None, _error(400, "invalid_request_error", "We could not parse the JSON body of your request.")
        with self._lock:
            self.requests.append(body)
            self.paths.append(request.url.path)
            self.headers.append(dict(request.headers))
        if not (request.headers.get("authorization") or "").startswith("Bearer "):
            return None, _error(401, "invalid_request_error", "You didn't provide an API key.")
        try:
            validate(body)
        except RequestError as error:
            return None, _error(400, "invalid_request_error", error.message, error.param)
        reply = self._next_reply(body)
        if reply.error is not None:
            return None, _error(reply.status, reply.error["type"], reply.error["message"])
        return (body, reply), None

    async def _wait(self) -> None:
        """Wait `delay` seconds, and count the requests that wait at the same time."""
        if not self.delay:
            return
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
        finally:
            with self._lock:
                self.in_flight -= 1

    async def _chat(self, request: Request) -> JSONResponse | StreamingResponse:
        received, failure = await self._receive(request, validate_chat_request)
        if failure is not None:
            return failure
        await self._wait()
        body, reply = received
        completion = _chat_completion(body, reply)
        if body.get("stream"):
            include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
            return StreamingResponse(_chat_chunks(completion, include_usage), media_type="text/event-stream")
        return JSONResponse(completion)

    async def _responses(self, request: Request) -> JSONResponse | StreamingResponse:
        received, failure = await self._receive(request, validate_responses_request)
        if failure is not None:
            return failure
        await self._wait()
        body, reply = received
        response = _response(body, reply)
        if body.get("stream"):
            return StreamingResponse(_response_events(response), media_type="text/event-stream")
        return JSONResponse(response)

    def app(self) -> Starlette:
        return Starlette(
            routes=[
                Route("/v1/chat/completions", self._chat, methods=["POST"]),
                Route("/v1/responses", self._responses, methods=["POST"]),
            ]
        )


# ---- helpers that checks also use ------------------------------------------


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for part in content or []:
        if isinstance(part, dict) and part.get("type") in {"text", "input_text", "output_text"}:
            parts.append(part.get("text", ""))
    return " ".join(parts)


def user_texts(body: dict[str, Any]) -> list[str]:
    """The text of each user message of a request, for both endpoints, in order."""
    if "messages" in body:
        return [_text_of(m.get("content")) for m in body["messages"] if m.get("role") == "user"]
    items = body.get("input")
    if isinstance(items, str):
        return [items]
    return [
        _text_of(item.get("content"))
        for item in items or []
        if item.get("role") == "user" and item.get("type", "message") == "message"
    ]


def first_user_text(body: dict[str, Any]) -> str:
    """The text of the first user message: the question of the conversation."""
    texts = user_texts(body)
    return texts[0] if texts else ""


def last_user_text(body: dict[str, Any]) -> str:
    """The text of the last user message."""
    texts = [text for text in user_texts(body) if text]
    return texts[-1] if texts else ""


def tool_outputs(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Each tool result of a request as {"call_id", "output"}, for both endpoints."""
    if "messages" in body:
        return [
            {"call_id": m.get("tool_call_id"), "output": _text_of(m.get("content"))}
            for m in body["messages"]
            if m.get("role") == "tool"
        ]
    items = body.get("input")
    return [
        {"call_id": item.get("call_id"), "output": _text_of(item.get("output"))}
        for item in ([] if isinstance(items, str) else items or [])
        if item.get("type") == "function_call_output"
    ]


def function_calls(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Each earlier function call in a request as {"call_id", "name", "arguments"}."""
    found = []
    if "messages" in body:
        for message in body["messages"]:
            for call in message.get("tool_calls") or []:
                function = call.get("function", {})
                found.append({"call_id": call.get("id"), "name": function.get("name"), "arguments": function.get("arguments")})
        return found
    items = body.get("input")
    for item in [] if isinstance(items, str) else items or []:
        if item.get("type") == "function_call":
            found.append({"call_id": item.get("call_id"), "name": item.get("name"), "arguments": item.get("arguments")})
    return found


def json_schema(body: dict[str, Any]) -> dict[str, Any] | None:
    """The JSON schema of structured output in a request, or None."""
    response_format = body.get("response_format") or {}
    if response_format.get("type") == "json_schema":
        return (response_format.get("json_schema") or {}).get("schema")
    text_format = (body.get("text") or {}).get("format") or {}
    if text_format.get("type") == "json_schema":
        return text_format.get("schema")
    return None


def wants_json(body: dict[str, Any]) -> bool:
    """True when the request asks for structured output (a JSON schema)."""
    return json_schema(body) is not None


def tool_names(body: dict[str, Any]) -> list[str]:
    """The names of the function tools of a request, for both endpoints."""
    names = []
    for tool in body.get("tools") or []:
        if "function" in tool:
            names.append(tool["function"].get("name"))
        elif tool.get("type") == "function":
            names.append(tool.get("name"))
    return names


def forced_tool(body: dict[str, Any]) -> str | None:
    """The name of the tool that tool_choice forces, or None."""
    choice = body.get("tool_choice")
    if isinstance(choice, dict):
        return (choice.get("function") or {}).get("name") or choice.get("name")
    return None


# ---- the rules of the real API that the fake also enforces ------------------


def validate_chat_request(body: dict[str, Any]) -> None:
    for name in ("model", "messages"):
        if name not in body:
            raise RequestError(f"Missing required parameter: '{name}'.", name)
    messages = body["messages"]
    if not messages:
        raise RequestError("Invalid 'messages': empty array. Expected an array with minimum length 1.", "messages")
    for index, tool in enumerate(body.get("tools") or []):
        if tool.get("type") != "function" or "name" not in (tool.get("function") or {}):
            raise RequestError(f"Missing required parameter: 'tools[{index}].function.name'.", f"tools[{index}]")
    open_calls: list[str] = []
    for index, message in enumerate(messages):
        role = message.get("role")
        if role == "tool":
            if message.get("tool_call_id") not in open_calls:
                raise RequestError(
                    f"Invalid parameter: messages with role 'tool' must be a response to a preceding "
                    f"message with 'tool_calls'. Unknown tool_call_id at messages[{index}].",
                    f"messages.[{index}].role",
                )
            open_calls.remove(message["tool_call_id"])
            continue
        if open_calls:
            raise RequestError(
                "An assistant message with 'tool_calls' must be followed by tool messages responding "
                f"to each 'tool_call_id'. The following tool_call_ids did not have response messages: "
                f"{', '.join(open_calls)}",
                f"messages.[{index}].role",
            )
        if role == "assistant":
            open_calls = [call["id"] for call in message.get("tool_calls") or []]
    if open_calls:
        raise RequestError(
            "An assistant message with 'tool_calls' must be followed by tool messages responding to "
            f"each 'tool_call_id'. The following tool_call_ids did not have response messages: {', '.join(open_calls)}",
            "messages",
        )


def validate_responses_request(body: dict[str, Any]) -> None:
    if "model" not in body:
        raise RequestError("Missing required parameter: 'model'.", "model")
    items = body.get("input")
    if items is None:
        raise RequestError("Missing required parameter: 'input'.", "input")
    for index, tool in enumerate(body.get("tools") or []):
        if tool.get("type") == "function" and "name" not in tool:
            raise RequestError(f"Missing required parameter: 'tools[{index}].name'.", f"tools[{index}].name")
    if isinstance(items, str):
        return
    calls = [item.get("call_id") for item in items if item.get("type") == "function_call"]
    outputs = [item.get("call_id") for item in items if item.get("type") == "function_call_output"]
    for call_id in outputs:
        if call_id not in calls:
            raise RequestError(f"No tool call found for function call output with call_id {call_id}.", "input")
    for call_id in calls:
        if call_id not in outputs:
            raise RequestError(f"No tool output found for function call {call_id}.", "input")


# ---- the responses ------------------------------------------------------------


def _usage_numbers(body: dict[str, Any], reply: Reply) -> tuple[int, int, int]:
    """(input tokens, output tokens, cached input tokens)."""
    if reply.usage is not None:
        return (
            reply.usage.get("input_tokens", 0),
            reply.usage.get("output_tokens", 0),
            reply.usage.get("cached_tokens", 0),
        )
    prompt = {key: body.get(key) for key in ("instructions", "input", "messages", "tools")}
    output = _tokens(reply.text or "") + sum(_tokens(call) for call in reply.tool_calls) if (reply.text or reply.tool_calls) else 1
    return _tokens(prompt), output, 0


def _chat_completion(body: dict[str, Any], reply: Reply) -> dict[str, Any]:
    input_tokens, output_tokens, cached = _usage_numbers(body, reply)
    tool_calls = [
        {"id": _next_id("call"), "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        for name, arguments in reply.tool_calls
    ]
    message: dict[str, Any] = {"role": "assistant", "content": reply.text, "refusal": None, "annotations": []}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": _next_id("chatcmpl"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body["model"],
        "choices": [
            {"index": 0, "message": message, "logprobs": None, "finish_reason": "tool_calls" if tool_calls else "stop"}
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "prompt_tokens_details": {"cached_tokens": cached, "audio_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0, "audio_tokens": 0},
        },
        "service_tier": "default",
        "system_fingerprint": None,
    }


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _chat_chunks(completion: dict[str, Any], include_usage: bool) -> Iterator[str]:
    """Yield the chunks that the real API streams for a chat completion."""
    base = {key: completion[key] for key in ("id", "created", "model", "service_tier", "system_fingerprint")}
    base["object"] = "chat.completion.chunk"

    def chunk(delta: dict[str, Any], finish_reason: str | None = None) -> str:
        data = dict(base, choices=[{"index": 0, "delta": delta, "logprobs": None, "finish_reason": finish_reason}])
        if include_usage:
            data["usage"] = None
        return f"data: {json.dumps(data)}\n\n"

    message = completion["choices"][0]["message"]
    yield chunk({"role": "assistant", "content": "", "refusal": None})
    if message.get("content"):
        for part in _chunks(message["content"], 12):
            yield chunk({"content": part})
    for index, call in enumerate(message.get("tool_calls") or []):
        opening = {"index": index, "id": call["id"], "type": "function", "function": {"name": call["function"]["name"], "arguments": ""}}
        yield chunk({"tool_calls": [opening]})
        for part in _chunks(call["function"]["arguments"], 16):
            yield chunk({"tool_calls": [{"index": index, "function": {"arguments": part}}]})
    yield chunk({}, completion["choices"][0]["finish_reason"])
    if include_usage:
        yield f"data: {json.dumps(dict(base, choices=[], usage=completion['usage']))}\n\n"
    yield "data: [DONE]\n\n"


def _response(body: dict[str, Any], reply: Reply) -> dict[str, Any]:
    input_tokens, output_tokens, cached = _usage_numbers(body, reply)
    output: list[dict[str, Any]] = []
    if reply.text is not None:
        output.append(
            {
                "type": "message",
                "id": _next_id("msg"),
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": reply.text, "annotations": [], "logprobs": []}],
            }
        )
    for name, arguments in reply.tool_calls:
        output.append(
            {
                "type": "function_call",
                "id": _next_id("fc"),
                "call_id": _next_id("call"),
                "name": name,
                "arguments": json.dumps(arguments),
                "status": "completed",
            }
        )
    now = int(time.time())
    return {
        "id": _next_id("resp"),
        "object": "response",
        "created_at": now,
        "completed_at": now,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": body.get("instructions"),
        "max_output_tokens": body.get("max_output_tokens"),
        "model": body["model"],
        "output": output,
        "parallel_tool_calls": body.get("parallel_tool_calls", True),
        "previous_response_id": body.get("previous_response_id"),
        "reasoning": {"effort": None, "summary": None},
        "store": body.get("store", True),
        "temperature": body.get("temperature", 1.0),
        "text": body.get("text") or {"format": {"type": "text"}},
        "tool_choice": body.get("tool_choice", "auto"),
        "tools": body.get("tools") or [],
        "top_p": body.get("top_p", 1.0),
        "truncation": "disabled",
        "usage": {
            "input_tokens": input_tokens,
            "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": 0},
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": input_tokens + output_tokens,
        },
        "user": None,
        "metadata": body.get("metadata") or {},
    }


def _response_events(response: dict[str, Any]) -> Iterator[str]:
    """Yield the event sequence that the real API streams for a response."""
    sequence = 0

    def event(kind: str, **data: Any) -> str:
        nonlocal sequence
        payload = {"type": kind, "sequence_number": sequence, **data}
        sequence += 1
        return f"event: {kind}\ndata: {json.dumps(payload)}\n\n"

    pending = dict(response, status="in_progress", output=[], usage=None, completed_at=None)
    yield event("response.created", response=pending)
    yield event("response.in_progress", response=pending)
    for index, item in enumerate(response["output"]):
        if item["type"] == "message":
            text = item["content"][0]["text"]
            yield event("response.output_item.added", output_index=index, item=dict(item, status="in_progress", content=[]))
            part = {"type": "output_text", "text": "", "annotations": [], "logprobs": []}
            yield event("response.content_part.added", item_id=item["id"], output_index=index, content_index=0, part=part)
            for piece in _chunks(text, 12):
                yield event(
                    "response.output_text.delta",
                    item_id=item["id"], output_index=index, content_index=0, delta=piece, logprobs=[],
                )
            yield event(
                "response.output_text.done", item_id=item["id"], output_index=index, content_index=0, text=text, logprobs=[]
            )
            yield event(
                "response.content_part.done", item_id=item["id"], output_index=index, content_index=0, part=item["content"][0]
            )
        else:
            yield event("response.output_item.added", output_index=index, item=dict(item, status="in_progress", arguments=""))
            for piece in _chunks(item["arguments"], 16):
                yield event("response.function_call_arguments.delta", item_id=item["id"], output_index=index, delta=piece)
            yield event(
                "response.function_call_arguments.done",
                item_id=item["id"], output_index=index, name=item["name"], arguments=item["arguments"],
            )
        yield event("response.output_item.done", output_index=index, item=item)
    yield event("response.completed", response=response)


def _error(status: int, error_type: str, message: str, param: str | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": error_type, "param": param, "code": None}}, status_code=status
    )


# ---- running the server ------------------------------------------------------


class FakeOpenAIServer:
    """Run a FakeOpenAI on a free localhost port, in a background thread."""

    def __init__(self) -> None:
        self.fake = FakeOpenAI()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.fake.url = f"http://127.0.0.1:{self.port}/v1"
        config = uvicorn.Config(self.fake.app(), host="127.0.0.1", port=self.port, log_level="error")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> FakeOpenAI:
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("The fake OpenAI API did not start.")
            time.sleep(0.02)
        return self.fake

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
