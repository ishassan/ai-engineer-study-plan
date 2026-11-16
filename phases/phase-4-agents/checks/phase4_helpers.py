"""Helpers of the Phase 4 checks: script the fake APIs of both providers in the same way.

The checks do not know how your code asks for structured output. A LangChain model can
ask for a JSON schema (output_config.format on Claude, response_format or text.format on
OpenAI) or force a tool call with the schema. The helpers read the request and answer in
the form that it asks for.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any, Callable

import httpx

from labkit import fake_claude, fake_openai
from labkit.sse import AskResult, parse_sse


# ---- what a request asks for ------------------------------------------------------------------


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref and ref.startswith("#/"):
        node: Any = root
        for part in ref[2:].split("/"):
            node = node[part]
        return _resolve(node, root)
    for key in ("anyOf", "allOf", "oneOf"):
        for option in schema.get(key) or []:
            found = _resolve(option, root)
            if found.get("type") != "null":
                return found
    return schema


def schema_of(body: dict[str, Any]) -> dict[str, Any] | None:
    """The JSON schema of the structured output that a request asks for, or None."""
    output_format = (body.get("output_config") or {}).get("format") or body.get("output_format") or {}
    if output_format.get("schema"):
        return output_format["schema"]
    found = fake_openai.json_schema(body)
    if found:
        return found
    forced = forced_tool(body)
    for tool in body.get("tools") or []:
        name = tool.get("name") or (tool.get("function") or {}).get("name")
        if forced and name == forced:
            return tool.get("input_schema") or tool.get("parameters") or (tool.get("function") or {}).get("parameters")
    return None


def forced_tool(body: dict[str, Any]) -> str | None:
    """The tool that tool_choice forces (a LangChain way to get structured output), or None."""
    choice = body.get("tool_choice")
    if isinstance(choice, dict) and choice.get("type") in {"tool", "function"}:
        return choice.get("name") or (choice.get("function") or {}).get("name")
    return None


def fields_of(body: dict[str, Any]) -> set[str]:
    schema = schema_of(body)
    return set(_resolve(schema, schema).get("properties", {})) if schema else set()


def asks_for_plan(body: dict[str, Any]) -> bool:
    return "steps" in fields_of(body)


def asks_for_answer(body: dict[str, Any]) -> bool:
    return "dataset_ids" in fields_of(body)


def citation_fields(body: dict[str, Any]) -> set[str]:
    """The fields of one citation in the answer schema of a request."""
    schema = schema_of(body)
    if not schema:
        return {"document_title", "page", "chunk_id"}
    citations = _resolve(schema, schema).get("properties", {}).get("citations")
    if not citations:
        return set()
    items = _resolve(_resolve(citations, schema).get("items", {}), schema)
    return set(items.get("properties", {}))


def has_tools(body: dict[str, Any]) -> bool:
    return bool(body.get("tools")) and not forced_tool(body)


def prompt_text(body: dict[str, Any]) -> str:
    """The whole prompt of a request as one text: system, messages and input."""
    parts = [body.get(key) for key in ("system", "instructions", "messages", "input")]
    return json.dumps([part for part in parts if part], ensure_ascii=False)


def prompt_size(body: dict[str, Any]) -> int:
    """The number of characters of the conversation in a request (system and messages)."""
    return len(prompt_text(body))


# ---- replies in the form that the request asks for --------------------------------------------


def structured(
    provider: str,
    value: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]],
    usage: dict[str, int] | None = None,
):
    """A reply that gives `value` as structured output, in the form that the request asks for."""

    def build(body: dict[str, Any]):
        data = value(body) if callable(value) else value
        forced = forced_tool(body)
        if provider == "openai":
            if forced and not fake_openai.wants_json(body):
                return fake_openai.tool_reply((forced, data), usage=openai_usage(usage))
            return fake_openai.json_reply(data, usage=openai_usage(usage))
        if forced:
            return fake_claude.tool_reply((forced, data), thinking=False, usage=usage)
        return fake_claude.json_reply(data, usage=usage)

    return build


def answer_value(body: dict[str, Any], text: str, dataset_ids: list[str] | None = None,
                 citations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """An answer for the schema of the request. A citation has the fields that the schema has."""
    fields = citation_fields(body)
    items = [{key: value for key, value in citation.items() if key in fields} for citation in citations or []]
    return {"answer": text, "dataset_ids": dataset_ids or [], "tools_called": [], "citations": items}


def openai_usage(usage: dict[str, int] | None) -> dict[str, int] | None:
    """Claude usage in the form of OpenAI: the input tokens hold the cached tokens."""
    if usage is None:
        return None
    cached = usage.get("cache_read_input_tokens", 0)
    return {"input_tokens": usage["input_tokens"] + cached, "output_tokens": usage["output_tokens"], "cached_tokens": cached}


def tool_call(provider: str, *calls: tuple[str, dict[str, Any]], usage: dict[str, int] | None = None):
    """A reply with tool calls. `usage` is in the form of Claude, for both providers."""
    if provider == "openai":
        return fake_openai.tool_reply(*calls, usage=openai_usage(usage))
    return fake_claude.tool_reply(*calls, usage=usage)


def fake_of(provider: str, fake: Any, fake_openai_api: Any) -> Any:
    return fake_openai_api if provider == "openai" else fake


# ---- the tool results in a request ------------------------------------------------------------


def tool_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Each tool result of a request as {"id", "output", "is_error"}, for both providers."""
    if "messages" in body and any(m.get("role") == "tool" for m in body["messages"]):
        return [{"id": r["call_id"], "output": r["output"], "is_error": None} for r in fake_openai.tool_outputs(body)]
    if "input" in body:
        return [{"id": r["call_id"], "output": r["output"], "is_error": None} for r in fake_openai.tool_outputs(body)]
    found = []
    for message in body.get("messages", []):
        content = message.get("content")
        for block in [] if isinstance(content, str) else content:
            if block.get("type") == "tool_result":
                output = block.get("content")
                if not isinstance(output, str):
                    output = " ".join(part.get("text", "") for part in output or [] if isinstance(part, dict))
                found.append({"id": block.get("tool_use_id"), "output": output, "is_error": block.get("is_error")})
    return found


def tool_calls(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Each earlier tool call in a request as {"id", "name"}, for both providers."""
    if "input" in body or any(m.get("tool_calls") for m in body.get("messages", [])):
        return [{"id": c["call_id"], "name": c["name"]} for c in fake_openai.function_calls(body)]
    found = []
    for message in body.get("messages", []):
        content = message.get("content")
        for block in [] if isinstance(content, str) else content:
            if block.get("type") == "tool_use":
                found.append({"id": block["id"], "name": block["name"]})
    return found


def returned_chunks(body: dict[str, Any]) -> list[dict[str, Any]]:
    """The results of search_documents in the tool results of a request."""
    chunks = []
    for result in tool_results(body):
        try:
            data = json.loads(result["output"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            data = next((value for value in data.values() if isinstance(value, list)), [])
        if isinstance(data, list):
            chunks += [item for item in data if isinstance(item, dict) and "chunk_id" in item]
    return chunks


# ---- the long-term memory ---------------------------------------------------------------------


def saved_facts(sql: Callable[..., list[dict[str, Any]]], user: str) -> list[dict[str, Any]]:
    """The facts of a user, each as {"text", "has_vector"}.

    Week 12 stores a fact in the table `memories`. Week 15 replaces it with the LangGraph
    store (PostgresStore): the tables `store` and `store_vectors`, with the user in the
    namespace. The checks accept both.
    """
    facts = sql("SELECT text, embedding IS NOT NULL AS has_vector FROM memories WHERE user_id = %s ORDER BY id", (user,))
    if sql("SELECT to_regclass('store_vectors') IS NOT NULL AS found")[0]["found"]:
        facts += sql(
            "SELECT s.value->>'text' AS text, bool_or(v.embedding IS NOT NULL) AS has_vector FROM store s "
            "LEFT JOIN store_vectors v ON v.prefix = s.prefix AND v.key = s.key "
            "WHERE %s = ANY(string_to_array(s.prefix, '.')) GROUP BY s.prefix, s.key, s.value, s.created_at "
            "ORDER BY s.created_at",
            (user,),
        )
    return [{"text": fact["text"], "has_vector": bool(fact["has_vector"])} for fact in facts]


# ---- the /ask endpoint ------------------------------------------------------------------------


def new_user() -> str:
    """A new user name, so that a check starts with no saved facts."""
    return f"check-{uuid.uuid4().hex[:12]}"


def _stream(response: Any) -> AskResult:
    return AskResult(
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        events=parse_sse(response.text) if response.status_code == 200 else [],
    )


def ask(client: Any, question: str, *, user: str | None = None, conversation_id: str | None = None) -> AskResult:
    """POST a question to /ask, with the user header and the conversation ID."""
    body: dict[str, Any] = {"question": question}
    if conversation_id:
        body["conversation_id"] = conversation_id
    headers = {"X-User": user} if user else {}
    return _stream(client.post("/ask", json=body, headers=headers))


def approve(client: Any, conversation_id: str, approved: bool, *, user: str | None = None) -> AskResult:
    """POST a decision to /approve. The user header is the approver."""
    headers = {"X-User": user} if user else {}
    body = {"conversation_id": conversation_id, "approved": approved}
    return _stream(client.post("/approve", json=body, headers=headers))


# ---- MCP clients ------------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _session(url: str, timeout: float):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(timeout=timeout) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def mcp_tools(url: str) -> dict[str, dict[str, Any]]:
    """The tools of an MCP server: {name: {"description", "input_schema"}}."""
    async def run() -> dict[str, dict[str, Any]]:
        async with _session(url, 30) as session:
            listed = await session.list_tools()
        return {tool.name: {"description": tool.description or "", "input_schema": tool.inputSchema}
                for tool in listed.tools}

    return asyncio.run(run())


def mcp_call(url: str, tool: str, arguments: dict[str, Any], timeout: float = 60) -> tuple[bool, Any]:
    """Call one tool of an MCP server. Return (is_error, value).

    The value is the JSON of the result when the result is JSON, else its text.
    """
    async def run() -> tuple[bool, Any]:
        async with _session(url, timeout) as session:
            result = await session.call_tool(tool, arguments)
        text = "".join(getattr(block, "text", "") for block in result.content)
        if not result.isError and result.structuredContent is not None:
            value = result.structuredContent
            if set(value) == {"result"}:
                value = value["result"]
            if isinstance(value, str):
                text = value
            else:
                return False, value
        try:
            return bool(result.isError), json.loads(text)
        except json.JSONDecodeError:
            return bool(result.isError), text

    return asyncio.run(run())
