"""The HTTP service. This file is complete: your work is in agent.py and llm.py.

POST /ask sends each event of answer_events() to the client as a server-sent
event:

    event: text
    data: {"text": "Three datasets"}

"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from assistant.agent import answer_events

logger = logging.getLogger("assistant.api")
app = FastAPI(title="Data platform assistant")


class AskRequest(BaseModel):
    question: str


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event_stream(question: str) -> Iterator[str]:
    try:
        for event, data in answer_events(question):
            yield sse(event, data)
    except Exception as error:
        # The response has started, so the status code cannot change any more.
        # Log the traceback and report the error inside the stream.
        logger.exception("The request failed")
        yield sse("error", {"message": f"{type(error).__name__}: {error}"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(body: AskRequest) -> StreamingResponse:
    return StreamingResponse(
        event_stream(body.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
