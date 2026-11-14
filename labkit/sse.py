"""Read the server-sent events of the /ask endpoint in the checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class AskResult:
    """The events of one /ask response, in the order they arrived."""

    status_code: int
    content_type: str
    events: list[tuple[str, dict[str, Any]]]

    def of(self, name: str) -> list[dict[str, Any]]:
        return [data for event, data in self.events if event == name]

    @property
    def names(self) -> list[str]:
        return [event for event, _ in self.events]

    @property
    def done(self) -> dict[str, Any]:
        found = self.of("done")
        assert found, (
            f"The stream has no `done` event. Events: {self.names}. "
            f"Errors: {[error.get('message') for error in self.errors]}"
        )
        assert self.names[-1] == "done", f"`done` must be the last event. Events: {self.names}"
        return found[0]

    @property
    def answer(self) -> dict[str, Any] | None:
        found = self.of("answer")
        return found[0] if found else None

    @property
    def errors(self) -> list[dict[str, Any]]:
        return self.of("error")

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self.of("tool")

    @property
    def text(self) -> str:
        """The answer text: the `answer` event if there is one, else the text events."""
        if self.answer is not None:
            return str(self.answer.get("answer", ""))
        return "".join(data.get("text", "") for data in self.of("text"))


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for chunk in body.replace("\r\n", "\n").split("\n\n"):
        name, data_lines = "message", []
        for line in chunk.split("\n"):
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if data_lines:
            events.append((name, json.loads("\n".join(data_lines))))
    return events


def ask(client: Any, question: str) -> AskResult:
    """POST a question to /ask and collect the events."""
    response = client.post("/ask", json={"question": question})
    return AskResult(
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        events=parse_sse(response.text) if response.status_code == 200 else [],
    )
