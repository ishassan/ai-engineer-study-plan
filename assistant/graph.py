"""Reference solution: the graph of Phase 4 with the token of the user (week 19)
and the design pattern of week 20 (approval of the risky tools after untrusted content)."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from functools import lru_cache
from typing import Annotated, Any, Iterator, TypedDict

from langchain_core.tools import BaseTool, ToolException
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, ToolMessage
from langfuse import get_client, observe
from langfuse.langchain import CallbackHandler
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, interrupt
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError

from assistant import conversations, memory, planner
from assistant.agent import SYSTEM_PROMPT
from assistant.auth import Identity, service_identity, service_token
from assistant.config import get_settings
from assistant.db import as_identity, connect
from assistant.models import chat_model, system_message, usage_of
from assistant.persistence import checkpointer
from assistant.planner import Plan
from assistant.tools import NEEDS_APPROVAL, TOOLS, run_tool

# Week 20, the design pattern: after the agent reads untrusted content, the tools that write or
# can send data out need the approval of a person, and the approval shows the reason. Each tool
# result that holds text of other people is untrusted: documents, catalogue entries, table rows.
UNTRUSTED_SOURCES = {"search_documents", "search_datasets", "get_dataset_schema", "get_dataset_stats", "run_sql"}
RISKY_TOOLS = {"save_memory", "register_dataset"}

REFUSED = (
    "A person refused this action, so {name} did not run and nothing changed. Tell the user that "
    "the action was refused. Do not call {name} again for this request."
)


class ChunkRef(BaseModel):
    chunk_id: str = Field(description="The chunk_id of a passage, copied exactly from search_documents.")


class GraphAnswer(BaseModel):
    """The answer of the model. Plain code adds the title and the page of each citation."""

    answer: str = Field(description="The answer to the user, in plain text.")
    dataset_ids: list[str] = Field(description="The id of each dataset that the answer uses.")
    tools_called: list[str] = Field(description="The name of each tool that you called.")
    citations: list[ChunkRef] = Field(
        default_factory=list, description="One item for each passage of search_documents that supports the answer."
    )


class State(TypedDict, total=False):
    # The checkpointer keeps the state of each conversation (thread_id = conversation_id).
    # `messages` grows over the questions of the conversation. The other keys belong to one
    # question: answer_events() sets them again at the start of each question (RUN_START).
    question: str
    user: str
    conversation_id: str
    facts: list[str]
    messages: Annotated[list[AnyMessage], add_messages]
    plan: list[str] | None
    failed: dict[str, Any] | None
    chunks: dict[str, dict[str, Any]]
    usage: list[dict[str, Any]]
    turns: int
    retried: bool
    approvals: dict[str, dict[str, Any]]
    # Week 20: the tools whose results the agent read in this conversation (not reset per question,
    # because the messages still hold the content).
    untrusted: list[str]
    answer: dict[str, Any] | None
    error: str | None
    stop: str | None


RUN_START: dict[str, Any] = {
    "plan": None, "failed": None, "chunks": {}, "usage": [], "turns": 0, "retried": False,
    "approvals": {}, "answer": None, "error": None, "stop": None,
}


def _system(state: State):
    texts = [SYSTEM_PROMPT]
    if state.get("facts"):
        texts.append(memory.facts_block([{"text": fact} for fact in state["facts"]]))
    return system_message(texts)


# ---- the tools --------------------------------------------------------------------------------


# The tools of the two MCP servers. The graph runs synchronously and the adapter tools are
# async only, so each call runs in its own event loop (asyncio.run). The client opens a new
# MCP session for each call.
LOCAL_TOOLS = {"search_documents", "save_memory"}


def _client(token: str) -> MultiServerMCPClient:
    """A client of both servers that sends the token of the user with each request (week 19)."""
    settings = get_settings()
    headers = {"Authorization": f"Bearer {token}"}
    return MultiServerMCPClient({
        "sql": {"url": settings.mcp_sql_url, "transport": "streamable_http", "headers": headers},
        "catalogue": {"url": settings.mcp_catalogue_url, "transport": "streamable_http", "headers": headers},
    })


@lru_cache
def _mcp_tools(sql_url: str, catalogue_url: str) -> tuple[dict[str, BaseTool], dict[str, str]]:
    """The definitions of the server tools (the same for each user) and the server of each tool.

    The list needs a token too: the service token. A tool call never uses these tool objects,
    because they hold the headers of the service token.
    """
    client, tools, servers = _client(service_token()), {}, {}
    for server in ("sql", "catalogue"):
        for tool in asyncio.run(client.get_tools(server_name=server)):
            tools[tool.name], servers[tool.name] = tool, server
    return tools, servers


def mcp_tools() -> dict[str, BaseTool]:
    settings = get_settings()
    return _mcp_tools(settings.mcp_sql_url, settings.mcp_catalogue_url)[0]


def _server_of(name: str) -> str | None:
    settings = get_settings()
    return _mcp_tools(settings.mcp_sql_url, settings.mcp_catalogue_url)[1].get(name)


def tool_definitions() -> list[Any]:
    return [*(tool for tool in TOOLS if tool["name"] in LOCAL_TOOLS), *mcp_tools().values()]


def call_tool(call: dict[str, Any], state: State, identity: Identity) -> str:
    """Run one tool call with the rights of `identity`. Raise an exception for an error."""
    if call["name"] in LOCAL_TOOLS:
        # The document search reads the chunks with the rights of the user (row security).
        with as_identity(identity):
            return run_tool(call["name"], call["args"], state["user"], state.get("conversation_id"))
    server = _server_of(call["name"])
    if server is None:
        raise ValueError(f"Unknown tool: {call['name']}")
    found = {tool.name: tool for tool in asyncio.run(_client(identity.token).get_tools(server_name=server))}
    tool = found[call["name"]]
    # An adapter tool is a LangChain tool: with the callbacks of the run it makes its own tool
    # observation in Langfuse, next to the one of run_tools. No callbacks here.
    tool_call = {"name": call["name"], "args": call["args"], "id": call["id"], "type": "tool_call"}
    message = asyncio.run(tool.ainvoke(tool_call, config={"callbacks": []}))
    text = message.content if isinstance(message.content, str) else "".join(
        block.get("text", "") for block in message.content if isinstance(block, dict)
    )
    if message.status == "error":
        raise ToolException(text)
    return text


def audit(state: State, call: dict[str, Any], result: str, approval: str, approver: str | None) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO audit_log (user_id, conversation_id, tool, arguments, result, approval, approver) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (state["user"], state.get("conversation_id"), call["name"], Jsonb(call["args"]), result, approval, approver),
        )


def approval_reason(call: dict[str, Any], state: State) -> str | None:
    """Why a call needs the approval of a person, or None when it does not."""
    read = sorted(set(state.get("untrusted") or []))
    if call["name"] in RISKY_TOOLS and read:
        return (f"The agent read untrusted content ({', '.join(read)}) before it asked for {call['name']}. "
                "That content can hold instructions of an attacker.")
    if call["name"] in NEEDS_APPROVAL:
        return f"{call['name']} changes the catalogue."
    return None


# ---- nodes ------------------------------------------------------------------------------------


def prepare(state: State) -> dict[str, Any]:
    return {"facts": [fact["text"] for fact in memory.search_facts(state["user"], state["question"])]}


def write_plan(state: State) -> dict[str, Any]:
    model = chat_model().with_structured_output(Plan, include_raw=True)
    out = model.invoke([system_message([planner.PLANNER_PROMPT.format(tools=planner.tool_list())]),
                        HumanMessage(state["question"])])
    plan = out["parsed"]
    get_stream_writer()(("plan", {"steps": plan.steps}))
    note = HumanMessage(f"Follow this plan:\n{planner.numbered(plan)}")
    return {"plan": plan.steps, "messages": [note], "usage": [*state["usage"], usage_of(out["raw"])]}


def change_plan(state: State) -> dict[str, Any]:
    failed = state["failed"]
    text = planner.REPLAN.format(
        question=state["question"],
        plan=planner.numbered(Plan(steps=state["plan"])),
        tool=failed["name"],
        tool_input=failed["input"],
        error=failed["error"],
    )
    model = chat_model().with_structured_output(Plan, include_raw=True)
    out = model.invoke([system_message([planner.PLANNER_PROMPT.format(tools=planner.tool_list())]), HumanMessage(text)])
    plan = out["parsed"]
    get_stream_writer()(("plan", {"steps": plan.steps}))
    note = HumanMessage(f"A step failed. Follow the new plan:\n{planner.numbered(plan)}")
    return {"plan": plan.steps, "failed": None, "messages": [note], "usage": [*state["usage"], usage_of(out["raw"])]}


def call_model(state: State) -> dict[str, Any]:
    model = chat_model().bind_tools(tool_definitions(), response_format=GraphAnswer)
    reply = model.invoke([_system(state), *state["messages"]])
    return {"messages": [reply], "usage": [*state["usage"], usage_of(reply)], "turns": state["turns"] + 1}


def approve(state: State) -> dict[str, Any]:
    """Pause the graph until a person decides. Only the interrupt is in this node.

    When the run continues, LangGraph runs the node again from its start, so no code that
    changes something may come before interrupt().
    """
    calls = [call for call in state["messages"][-1].tool_calls if approval_reason(call, state)]
    decision = interrupt([{"id": call["id"], "name": call["name"], "input": call["args"],
                           "reason": approval_reason(call, state)} for call in calls])
    return {"approvals": {call["id"]: {"approved": bool(decision.get("approved")), "approver": decision.get("approver")}
                          for call in calls}}


def run_tools(state: State, config: RunnableConfig) -> dict[str, Any]:
    writer = get_stream_writer()
    identity = config["configurable"]["identity"]
    reply = state["messages"][-1]
    results, chunks, failed = [], dict(state.get("chunks") or {}), None
    untrusted = list(state.get("untrusted") or [])
    for call in reply.tool_calls:
        approval, approver = "not_needed", None
        if approval_reason(call, state):
            decision = (state.get("approvals") or {}).get(call["id"]) or {}
            approval = "approved" if decision.get("approved") else "refused"
            approver = decision.get("approver") or "unknown"
        with get_client().start_as_current_observation(as_type="tool", name=call["name"], input=call["args"]) as span:
            if approval == "refused":
                output, is_error = REFUSED.format(name=call["name"]), True
                span.update(output=output)
            else:
                try:
                    output, is_error = call_tool(call, state, identity), False
                    span.update(output=output)
                except Exception as error:
                    output, is_error = f"{type(error).__name__}: {error}", True
                    span.update(output=output, level="ERROR", status_message=output)
                    failed = failed or {"name": call["name"], "input": call["args"], "error": output}
        audit(state, call, output, approval, approver)
        if call["name"] in UNTRUSTED_SOURCES and not is_error:
            untrusted.append(call["name"])
        if call["name"] == "search_documents" and not is_error:
            for row in json.loads(output):
                chunks[row["chunk_id"]] = {"document_title": row["title"], "page": row["page"]}
        results.append(ToolMessage(content=output, tool_call_id=call["id"], status="error" if is_error else "success"))
        writer(("tool", {"name": call["name"], "input": call["args"], "is_error": is_error}))
    return {"messages": results, "chunks": chunks, "failed": failed if state.get("plan") else None,
            "untrusted": untrusted}


def finish(state: State) -> dict[str, Any]:
    """Plain code: check the answer, and format the citations from the search results."""
    reply = state["messages"][-1]
    try:
        answer = GraphAnswer.model_validate_json(reply.text)
    except ValidationError as error:
        return {"error": f"The answer is not valid: {error.errors()[0]['msg']}", "stop": "final"}
    known = state.get("chunks") or {}
    wrong = sorted({c.chunk_id for c in answer.citations} - set(known))
    if wrong and not state.get("retried"):
        feedback = HumanMessage(
            "Your answer cites chunk ids that search_documents did not return in this conversation: "
            f"{', '.join(wrong)}. Give the answer again. Cite only chunk ids from the tool results, "
            "or search again first."
        )
        return {"retried": True, "messages": [feedback]}
    if wrong:
        return {"error": f"The answer cites unknown chunk ids: {', '.join(wrong)}", "stop": "final"}
    citations = [{**known[c.chunk_id], "chunk_id": c.chunk_id} for c in answer.citations]
    value = {"answer": answer.answer, "dataset_ids": answer.dataset_ids, "tools_called": answer.tools_called,
             "citations": citations}
    get_stream_writer()(("answer", value))
    return {"answer": value, "stop": "final"}


def _transcript(messages: list[AnyMessage]) -> str:
    lines = []
    for message in messages:
        if isinstance(message, ToolMessage):
            lines.append(f"[tool result {message.text[:300]}]")
            continue
        role = "user" if isinstance(message, HumanMessage) else "assistant"
        calls = " ".join(f"[tool call {c['name']} {json.dumps(c['args'], ensure_ascii=False)}]"
                         for c in getattr(message, "tool_calls", []) or [])
        text = " ".join(part for part in (message.text, calls) if part)
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def save(state: State) -> dict[str, Any]:
    """Compaction: when the context is near the limit, replace the messages with a summary."""
    last = (state.get("usage") or [{}])[-1]
    size = sum(last.get(key, 0) for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    if size < get_settings().compact_at_tokens:
        return {}
    summary = chat_model().invoke([system_message([memory.SUMMARY_PROMPT]), HumanMessage(_transcript(state["messages"]))])
    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            HumanMessage(f"{memory.SUMMARY_PREFIX}\n{summary.text}"),
            AIMessage("I will use this summary in the rest of the conversation."),
        ],
        "usage": [*state["usage"], usage_of(summary)],
    }


# ---- edges ------------------------------------------------------------------------------------


def after_prepare(state: State) -> str:
    return "write_plan" if get_settings().planner else "call_model"


def after_model(state: State) -> str:
    calls = state["messages"][-1].tool_calls
    if calls and state.get("turns", 0) >= get_settings().max_turns:
        return "save"
    if not calls:
        return "finish"
    return "approve" if any(approval_reason(call, state) for call in calls) else "run_tools"


def after_tools(state: State) -> str:
    return "change_plan" if state.get("failed") else "call_model"


def after_finish(state: State) -> str:
    return "save" if state.get("stop") or state.get("turns", 0) >= get_settings().max_turns else "call_model"


def build_graph():
    graph = StateGraph(State)
    for node in (prepare, write_plan, change_plan, call_model, approve, run_tools, finish, save):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", after_prepare, ["write_plan", "call_model"])
    graph.add_edge("write_plan", "call_model")
    graph.add_conditional_edges("call_model", after_model, ["approve", "run_tools", "finish", "save"])
    graph.add_edge("approve", "run_tools")
    graph.add_conditional_edges("run_tools", after_tools, ["change_plan", "call_model"])
    graph.add_edge("change_plan", "call_model")
    graph.add_conditional_edges("finish", after_finish, ["save", "call_model"])
    graph.add_edge("save", END)
    return graph.compile(checkpointer=checkpointer())


def _config(conversation_id: str, identity: Identity) -> dict[str, Any]:
    # The identity is an object, not a string: LangGraph copies only plain values of
    # `configurable` into the metadata of a checkpoint, so the token is not stored in Postgres.
    return {"configurable": {"thread_id": conversation_id, "identity": identity}, "callbacks": [CallbackHandler()],
            "recursion_limit": 4 * get_settings().max_turns + 10}


def _run(graph: Any, value: Any, config: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    settings = get_settings()
    started = time.perf_counter()
    # durability="sync": each step is in Postgres before the next step starts.
    for chunk in graph.stream(value, config, stream_mode="custom", durability="sync"):
        yield chunk
    snapshot = graph.get_state(config)
    state = snapshot.values
    if snapshot.interrupts:
        for pending in snapshot.interrupts:
            for call in pending.value:
                yield "approval", {"name": call["name"], "input": call["input"], "reason": call.get("reason")}
        stop = "approval"
    else:
        if state.get("error"):
            yield "error", {"message": state["error"]}
        stop = state.get("stop") or "max_turns"
        if stop == "max_turns":
            yield "error", {"message": f"No final answer after {settings.max_turns} turns."}
    usage = state.get("usage") or []
    totals = {key: sum(u[key] for u in usage) for key in
              ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "cost_usd")}
    model = next((u["model"] for u in reversed(usage) if u["model"]), settings.model)
    latency = round((time.perf_counter() - started) * 1000, 1)
    yield "done", {"model": model, **totals, "latency_ms": latency, "requests": len(usage), "stop": stop}


@observe(name="ask", as_type="agent")
def answer_events(
    question: str, conversation_id: str | None = None, user: str = "anonymous", identity: Identity | None = None
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Answer one question. The API passes the identity of the token. A job without a person
    (an evaluation) passes none, and the graph uses the service account."""
    conversation_id = conversation_id or str(uuid.uuid4())
    identity = identity or service_identity()
    # The checkpointer has no owner for a thread: the table conversations has.
    conversations.open_conversation(conversation_id, user)
    graph, config = build_graph(), _config(conversation_id, identity)
    if graph.get_state(config).interrupts:
        raise RuntimeError("This conversation waits for an approval. Send POST /approve first.")
    start = {"question": question, "user": user, "conversation_id": conversation_id,
             "messages": [HumanMessage(question)], **RUN_START}
    yield from _run(graph, start, config)


@observe(name="approve", as_type="agent")
def resume_events(
    conversation_id: str, approved: bool, approver: str, identity: Identity | None = None
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Go on after a decision. The tools of the rest of the run use the token of the approver."""
    graph, config = build_graph(), _config(conversation_id, identity or service_identity())
    if not graph.get_state(config).interrupts:
        raise LookupError(f"Nothing in the conversation {conversation_id} waits for an approval.")
    yield from _run(graph, Command(resume={"approved": approved, "approver": approver}), config)
