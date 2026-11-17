"""Helpers of the Phase 5 checks: tokens, MCP clients with a token, and the tool results of a request."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any, Callable

import httpx

from labkit import fake_claude
from labkit.sse import AskResult, parse_sse

USERS = ("viewer", "analyst", "auditor")
POPULATION = "population-by-gender-age-nationality-saudinon-saudi"
RESTRICTED_DOCUMENT = "gastat-business-confidence"
# One value of data.population (2014, Male, Saudi). Only a reader of the dataset can see it.
POPULATION_VALUE = "7812695"


def fake_auth() -> Any:
    from labkit import auth

    assert auth.FAKE is not None, "The fake authorization server of labkit does not run (PyJWT is missing?)."
    return auth.FAKE


def token(user: str, **options: Any) -> str:
    """A token of the fake authorization server for a user, with the claims of the realm `lab`."""
    return fake_auth().mint(user, **options)


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def new_user() -> str:
    return f"check-{uuid.uuid4().hex[:12]}"


MISTAKES = ("expired", "signed with another key", "of another issuer", "for another audience",
            "without the scope mcp:tools", "not a token")


def bad_tokens(audience: str) -> dict[str, str]:
    """Tokens that a service with this audience must refuse, by the name of the mistake."""
    from labkit.auth import AUDIENCES, new_key

    others = tuple(name for name in AUDIENCES if name != audience)
    return {
        "expired": token("analyst", expires_in=-600),
        "signed with another key": token("analyst", key=new_key()),
        "of another issuer": token("analyst", issuer="http://localhost:9999/realms/other"),
        "for another audience": token("analyst", audience=others),
        "without the scope mcp:tools": token("analyst", scope="openid profile"),
        "not a token": "not-a-token",
    }


def stream(response: Any) -> AskResult:
    return AskResult(
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        events=parse_sse(response.text) if response.status_code == 200 else [],
    )


def ask(client: Any, question: str, headers: dict[str, str]) -> AskResult:
    return stream(client.post("/ask", json={"question": question}, headers=headers))


# ---- MCP ------------------------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _session(url: str, headers: dict[str, str], timeout: float):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def mcp_tool_names(url: str, headers: dict[str, str]) -> set[str]:
    async def run() -> set[str]:
        async with _session(url, headers, 30) as session:
            return {tool.name for tool in (await session.list_tools()).tools}

    return asyncio.run(run())


def mcp_call(url: str, headers: dict[str, str], tool: str, arguments: dict[str, Any]) -> tuple[bool, Any]:
    """Call one tool with these headers. Return (is_error, value): the JSON of the result, else its text."""
    async def run() -> tuple[bool, Any]:
        async with _session(url, headers, 60) as session:
            result = await session.call_tool(tool, arguments)
        text = "".join(getattr(block, "text", "") for block in result.content)
        if not result.isError and result.structuredContent is not None:
            value = result.structuredContent
            if set(value) == {"result"}:
                value = value["result"]
            if not isinstance(value, str):
                return False, value
            text = value
        try:
            return bool(result.isError), json.loads(text)
        except json.JSONDecodeError:
            return bool(result.isError), text

    return asyncio.run(run())


def initialize(url: str, headers: dict[str, str]) -> httpx.Response:
    """One raw `initialize` request of the MCP protocol, to read the status code."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "lab-check", "version": "1"}}}
    return httpx.post(url, json=body, timeout=30,
                      headers={"Accept": "application/json, text/event-stream", **headers})


def rows_of(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return value.get("rows") or []
    return []


def first_value(value: Any) -> Any:
    """The first value of the first row of a run_sql result (a row can be a list or an object)."""
    rows = rows_of(value)
    if not rows:
        return None
    row = rows[0]
    return next(iter(row.values()), None) if isinstance(row, dict) else (row[0] if row else None)


# ---- the requests that the fake received -------------------------------------------------------------


def tool_results(body: dict[str, Any]) -> list[str]:
    found = []
    for message in body.get("messages", []):
        content = message.get("content")
        for block in [] if isinstance(content, str) else content:
            if block.get("type") == "tool_result":
                output = block.get("content")
                if not isinstance(output, str):
                    output = " ".join(part.get("text", "") for part in output or [] if isinstance(part, dict))
                found.append(output)
    return found


def results_of(fake: Any) -> list[str]:
    """Each tool result of the conversation, from the last request that the fake received."""
    return tool_results(fake.requests[-1]) if fake.requests else []


def last_results(fake: Any) -> str:
    """All tool results that the fake received, as one text."""
    return "\n".join(text for body in fake.requests for text in tool_results(body))


def answer_for(text: str) -> Callable[[dict[str, Any]], fake_claude.Reply]:
    """A final answer in the form that the request asks for."""
    def build(body: dict[str, Any]) -> fake_claude.Reply:
        if fake_claude.wants_json(body):
            return fake_claude.json_reply({"answer": text, "dataset_ids": [], "tools_called": [], "citations": []})
        return fake_claude.text_reply(text)

    return build
