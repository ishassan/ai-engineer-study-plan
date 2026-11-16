"""The HTTP service. This is the Phase 4 copy of the file, and it is complete.

POST /ask sends each event of answer_events() to the client as a server-sent
event:

    event: text
    data: {"text": "Three datasets"}

Changes from Phase 1:

- The body can have `conversation_id`. Without it, the service starts a new
  conversation. The `done` event of each stream reports the ID, so the client can
  send it with the next question.
- The user comes from the header `X-User` (default `anonymous`). Only
  current_user() reads it: Phase 5 replaces the header with a sign-in token there.
- The setting AGENT_IMPL chooses the loop: `handwritten` (assistant/agent.py) or
  `langgraph` (assistant/graph.py). Both give the same events.

Week 15: approval of write actions. When the graph pauses before a tool that needs an
approval, the stream of /ask sends one `approval` event for each such tool call and ends
with `done` (`stop: "approval"`). POST /approve continues the run:

    POST /approve   {"conversation_id": "...", "approved": true}

The approver is the user of the request (the header X-User). The response is the same kind
of event stream as /ask. It calls resume_events() of assistant/graph.py, so approval works
only with AGENT_IMPL=langgraph.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, Iterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from assistant.config import get_settings

logger = logging.getLogger("assistant.api")
app = FastAPI(title="Data platform assistant")

AnswerEvents = Callable[..., Iterator[tuple[str, dict[str, Any]]]]


class AskRequest(BaseModel):
    question: str
    conversation_id: str | None = None


class ApproveRequest(BaseModel):
    conversation_id: str
    approved: bool


def current_user(request: Request) -> str:
    """The user of a request. This is the only place that reads it."""
    return request.headers.get("X-User", "").strip() or "anonymous"


def agent() -> AnswerEvents:
    """The answer_events() function of the loop that AGENT_IMPL chooses."""
    if get_settings().agent_impl == "langgraph":
        from assistant.graph import answer_events
    else:
        from assistant.agent import answer_events
    return answer_events


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event_stream(start: Callable[[], Iterator[tuple[str, dict[str, Any]]]], conversation_id: str) -> Iterator[str]:
    try:
        for event, data in start():
            if event == "done":
                data = {**data, "conversation_id": conversation_id}
            yield sse(event, data)
    except Exception as error:
        # The response has started, so the status code cannot change any more.
        # Log the traceback and report the error inside the stream.
        logger.exception("The request failed")
        yield sse("error", {"message": f"{type(error).__name__}: {error}"})
        yield sse("done", {"stop": "error", "conversation_id": conversation_id})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def streaming(events: Iterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/ask")
def ask(body: AskRequest, request: Request) -> StreamingResponse:
    conversation_id = body.conversation_id or str(uuid.uuid4())
    user = current_user(request)
    return streaming(event_stream(
        lambda: agent()(body.question, conversation_id=conversation_id, user=user), conversation_id
    ))


def resume(conversation_id: str, approved: bool, approver: str) -> Iterator[tuple[str, dict[str, Any]]]:
    if get_settings().agent_impl != "langgraph":
        raise RuntimeError("Approval needs the graph. Set AGENT_IMPL=langgraph.")
    from assistant.graph import resume_events

    return resume_events(conversation_id, approved=approved, approver=approver)


@app.post("/approve")
def approve(body: ApproveRequest, request: Request) -> StreamingResponse:
    approver = current_user(request)
    return streaming(event_stream(
        lambda: resume(body.conversation_id, body.approved, approver), body.conversation_id
    ))
