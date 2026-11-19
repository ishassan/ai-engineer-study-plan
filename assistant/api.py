"""Reference solution: the HTTP service with sign-in (week 19), the
input and output checks of NeMo Guardrails (week 20), and the feedback of the user (Phase 7, week 26).

The Phase 4 copy. current_user() reads the access token, and the graph gets the identity.

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
from typing import Any, Callable, Iterator, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langfuse import get_client
from pydantic import BaseModel, Field

from assistant.auth import Identity, verify
from assistant.config import get_settings
from assistant.guardrails import check_input, check_output

logger = logging.getLogger("assistant.api")
app = FastAPI(title="Data platform assistant")

AnswerEvents = Callable[..., Iterator[tuple[str, dict[str, Any]]]]


class AskRequest(BaseModel):
    question: str
    conversation_id: str | None = None


class ApproveRequest(BaseModel):
    conversation_id: str
    approved: bool


class FeedbackRequest(BaseModel):
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    rating: Literal["good", "bad"]
    comment: str | None = Field(default=None, max_length=2000)


def current_user(request: Request) -> Identity:
    """The identity of the access token of a request. Week 19: the header X-User is not read.

    A request without a valid token gets 401, before the stream starts.
    """
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    identity = verify(token.strip(), get_settings().api_audience) if scheme.lower() == "bearer" else None
    if identity is None:
        raise HTTPException(status_code=401, detail="A valid access token is needed.",
                            headers={"WWW-Authenticate": 'Bearer realm="assistant"'})
    return identity


def run_agent(question: str, conversation_id: str, identity: Identity) -> Iterator[tuple[str, dict[str, Any]]]:
    """The events of the loop of AGENT_IMPL. The graph gets the identity with its token."""
    if get_settings().agent_impl == "langgraph":
        from assistant.graph import answer_events

        return answer_events(question, conversation_id=conversation_id, user=identity.user, identity=identity)
    return agent()(question, conversation_id=conversation_id, user=identity.user)


def guarded(question: str | None, events: Callable[[], Iterator[tuple[str, dict[str, Any]]]]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Week 20: check the question before the agent runs, and the answer before the user sees it.

    A blocked question gets the refusal of the rails as its answer, and the agent does not run.
    The answer goes out after the output rails (they mask links, e-mail addresses, phone and card
    numbers). The text events of the hand-written loop are kept back and sent as one checked
    text, because a rail cannot check half a sentence. After an approval (question None) there is
    no new question, but the answer still goes through the output rails.
    """
    if not get_settings().guardrails_url:
        yield from events()
        return
    check = check_input(question) if question is not None else None
    if check is not None and check.blocked:
        yield "answer", {"answer": check.content, "dataset_ids": [], "tools_called": [], "citations": []}
        yield "done", {"stop": "blocked", "rail": check.rail}
        return
    text: list[str] = []
    for event, data in events():
        if event == "text":
            text.append(data.get("text", ""))
            continue
        if event in {"answer", "done"} and text:
            yield "text", {"text": check_output(question or "", "".join(text)).content}
            text = []
        if event == "answer":
            data = {**data, "answer": check_output(question or "", str(data.get("answer", ""))).content}
        yield event, data


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
    identity = current_user(request)
    return streaming(event_stream(
        lambda: guarded(body.question, lambda: run_agent(body.question, conversation_id, identity)), conversation_id
    ))


def resume(conversation_id: str, approved: bool, approver: Identity) -> Iterator[tuple[str, dict[str, Any]]]:
    if get_settings().agent_impl != "langgraph":
        raise RuntimeError("Approval needs the graph. Set AGENT_IMPL=langgraph.")
    from assistant.graph import resume_events

    return resume_events(conversation_id, approved=approved, approver=approver.user, identity=approver)


@app.post("/approve")
def approve(body: ApproveRequest, request: Request) -> StreamingResponse:
    approver = current_user(request)
    return streaming(event_stream(
        lambda: guarded(None, lambda: resume(body.conversation_id, body.approved, approver)), body.conversation_id
    ))


@app.post("/feedback", status_code=204)
def feedback(body: FeedbackRequest, request: Request) -> None:
    """Week 26: store the rating of one answer as a score on the trace of its request."""
    identity = current_user(request)
    get_client().create_score(
        name="user-feedback",
        value=1 if body.rating == "good" else 0,
        data_type="BOOLEAN",
        trace_id=body.trace_id,
        comment=body.comment or None,
        metadata={"user": identity.user},
    )
