"""Reference solution. Input and output checks with the NeMo Guardrails server. Phase 5, week 20.

The server runs in Docker (`make up` with phase 5, service `guardrails`) with the configuration
guardrails/config/assistant/config.yml: the jailbreak heuristics and the Presidio check on the
input, and the Presidio masking on the output. GUARDRAILS_URL is its address
(http://localhost:8100); when the setting is empty, the API makes no checks.

The endpoint is POST {GUARDRAILS_URL}/v1/checks. The body is a chat request with the extra key
`guardrails`:

    {"model": "none",
     "messages": [{"role": "user", "content": "..."}],
     "guardrails": {"config_ids": ["assistant"], "rail_types": ["input"]}}

For the output, send the question and the answer ({"role": "assistant", ...}) with
"rail_types": ["output"]. The response is {"status": "passed" | "modified" | "blocked",
"content": "...", "rail": "..."}: `content` is the text after the rails (the refusal when the
status is blocked, the masked answer when it is modified).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from assistant.config import get_settings


@dataclass(frozen=True)
class Check:
    """The result of one check: the status, the text after the rails, the rail that blocked."""

    status: str
    content: str
    rail: str | None = None

    @property
    def blocked(self) -> bool:
        return self.status == "blocked"


def _check(messages: list[dict[str, str]], rail_type: str) -> Check:
    settings = get_settings()
    body = {"model": "none", "messages": messages,
            "guardrails": {"config_ids": [settings.guardrails_config_id], "rail_types": [rail_type]}}
    response = httpx.post(f"{settings.guardrails_url}/v1/checks", json=body, timeout=60)
    response.raise_for_status()
    data = response.json()
    return Check(status=data["status"], content=data.get("content", ""), rail=data.get("rail"))


def check_input(question: str) -> Check:
    """Run the input rails on a question."""
    return _check([{"role": "user", "content": question}], "input")


def check_output(question: str, answer: str) -> Check:
    """Run the output rails on an answer to a question."""
    return _check([{"role": "user", "content": question}, {"role": "assistant", "content": answer}], "output")
