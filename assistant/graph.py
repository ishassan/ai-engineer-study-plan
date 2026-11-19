"""Reference solution: the agent as a LangGraph graph."""

from __future__ import annotations

import json
import operator
import time
from typing import Annotated, Any, Iterator, TypedDict

import psycopg
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langfuse import get_client, observe
from langfuse.langchain import CallbackHandler
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, ValidationError

from assistant import conversations, memory, planner
from assistant.agent import SYSTEM_PROMPT
from assistant.config import get_settings
from assistant.models import chat_model, system_message, usage_of
from assistant.planner import Plan
from assistant.tools import TOOLS, run_tool


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
    question: str
    user: str
    conversation_id: str | None
    history: list[AnyMessage]
    facts: list[str]
    messages: Annotated[list[AnyMessage], add_messages]
    plan: list[str] | None
    failed: dict[str, Any] | None
    chunks: Annotated[dict[str, dict[str, Any]], operator.or_]
    usage: Annotated[list[dict[str, Any]], operator.add]
    turns: Annotated[int, operator.add]
    retried: bool
    answer: dict[str, Any] | None
    error: str | None
    stop: str


def _history(messages: list[dict[str, Any]]) -> list[AnyMessage]:
    """Stored messages as LangChain messages: the text of each turn, without tool calls."""
    found: list[AnyMessage] = []
    for message in messages:
        content = message["content"]
        text = content if isinstance(content, str) else " ".join(
            block.get("text", "") for block in content if block.get("type") == "text"
        )
        if text:
            found.append(HumanMessage(text) if message["role"] == "user" else AIMessage(text))
    return found


def _system(state: State):
    texts = [SYSTEM_PROMPT]
    if state.get("facts"):
        texts.append(memory.facts_block([{"text": fact} for fact in state["facts"]]))
    return system_message(texts)


# ---- nodes ------------------------------------------------------------------------------------


def prepare(state: State) -> dict[str, Any]:
    history: list[AnyMessage] = []
    facts: list[str] = []
    conversation_id = state.get("conversation_id")
    try:
        if conversation_id:
            conversations.open_conversation(conversation_id, state["user"])
            history = _history(conversations.load_context(conversation_id))
        facts = [fact["text"] for fact in memory.search_facts(state["user"], state["question"])]
    except psycopg.OperationalError:
        conversation_id = None  # Without the database the graph still answers.
    return {"history": history, "facts": facts, "messages": [HumanMessage(state["question"])], "chunks": {},
            "conversation_id": conversation_id}


def write_plan(state: State) -> dict[str, Any]:
    model = chat_model().with_structured_output(Plan, include_raw=True)
    out = model.invoke([system_message([planner.PLANNER_PROMPT.format(tools=planner.tool_list())]),
                        HumanMessage(state["question"])])
    plan = out["parsed"]
    get_stream_writer()(("plan", {"steps": plan.steps}))
    note = HumanMessage(f"Follow this plan:\n{planner.numbered(plan)}")
    return {"plan": plan.steps, "messages": [note], "usage": [usage_of(out["raw"])]}


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
    return {"plan": plan.steps, "failed": None, "messages": [note], "usage": [usage_of(out["raw"])]}


def call_model(state: State) -> dict[str, Any]:
    model = chat_model().bind_tools(TOOLS, response_format=GraphAnswer)
    reply = model.invoke([_system(state), *state.get("history", []), *state["messages"]])
    return {"messages": [reply], "usage": [usage_of(reply)], "turns": 1}


def run_tools(state: State) -> dict[str, Any]:
    writer = get_stream_writer()
    reply = state["messages"][-1]
    results, chunks, failed = [], {}, None
    for call in reply.tool_calls:
        with get_client().start_as_current_observation(as_type="tool", name=call["name"], input=call["args"]) as span:
            try:
                output = run_tool(call["name"], call["args"], state["user"], state.get("conversation_id"))
                is_error = False
                span.update(output=output)
            except Exception as error:
                output, is_error = f"{type(error).__name__}: {error}", True
                span.update(output=output, level="ERROR", status_message=output)
                failed = failed or {"name": call["name"], "input": call["args"], "error": output}
        if call["name"] == "search_documents" and not is_error:
            for row in json.loads(output):
                chunks[row["chunk_id"]] = {"document_title": row["title"], "page": row["page"]}
        results.append(ToolMessage(content=output, tool_call_id=call["id"], status="error" if is_error else "success"))
        writer(("tool", {"name": call["name"], "input": call["args"], "is_error": is_error}))
    return {"messages": results, "chunks": chunks, "failed": failed if state.get("plan") else None}


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


def save(state: State) -> dict[str, Any]:
    settings = get_settings()
    conversation_id = state.get("conversation_id")
    if not conversation_id:
        return {}
    answer = state.get("answer")
    reply = json.dumps(answer, ensure_ascii=False) if answer else "I could not finish the answer."
    turn = [{"role": "user", "content": state["question"]}, {"role": "assistant", "content": reply}]
    conversations.append_messages(conversation_id, turn)
    last = (state.get("usage") or [{}])[-1]
    size = sum(last.get(key, 0) for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    if size < settings.compact_at_tokens:
        return {}
    old = [{"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.text}
           for m in state.get("history", [])] + turn
    summary = chat_model().invoke([system_message([memory.SUMMARY_PROMPT]), HumanMessage(memory.transcript(old))])
    conversations.start_new_context(conversation_id, [
        {"role": "user", "content": f"{memory.SUMMARY_PREFIX}\n{summary.text}"},
        {"role": "assistant", "content": "I will use this summary in the rest of the conversation."},
    ])
    return {"usage": [usage_of(summary)]}


# ---- edges ------------------------------------------------------------------------------------


def after_prepare(state: State) -> str:
    return "write_plan" if get_settings().planner else "call_model"


def after_model(state: State) -> str:
    if state["messages"][-1].tool_calls and state.get("turns", 0) >= get_settings().max_turns:
        return "save"
    return "run_tools" if state["messages"][-1].tool_calls else "finish"


def after_tools(state: State) -> str:
    return "change_plan" if state.get("failed") else "call_model"


def after_finish(state: State) -> str:
    return "save" if state.get("stop") or state.get("turns", 0) >= get_settings().max_turns else "call_model"


def build_graph():
    graph = StateGraph(State)
    for node in (prepare, write_plan, change_plan, call_model, run_tools, finish, save):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", after_prepare, ["write_plan", "call_model"])
    graph.add_edge("write_plan", "call_model")
    graph.add_conditional_edges("call_model", after_model, ["run_tools", "finish", "save"])
    graph.add_conditional_edges("run_tools", after_tools, ["change_plan", "call_model"])
    graph.add_edge("change_plan", "call_model")
    graph.add_conditional_edges("finish", after_finish, ["save", "call_model"])
    graph.add_edge("save", END)
    return graph.compile()


@observe(name="ask", as_type="agent")
def answer_events(
    question: str, conversation_id: str | None = None, user: str = "anonymous"
) -> Iterator[tuple[str, dict[str, Any]]]:
    settings = get_settings()
    started = time.perf_counter()
    state: dict[str, Any] = {}
    config = {"callbacks": [CallbackHandler()], "recursion_limit": 4 * settings.max_turns + 10}
    start = {"question": question, "user": user, "conversation_id": conversation_id}
    for mode, chunk in build_graph().stream(start, config, stream_mode=["custom", "values"]):
        if mode == "custom":
            yield chunk
        else:
            state = chunk
    usage = state.get("usage") or []
    if state.get("error"):
        yield "error", {"message": state["error"]}
    stop = state.get("stop") or "max_turns"
    if stop == "max_turns":
        yield "error", {"message": f"No final answer after {settings.max_turns} turns."}
    totals = {key: sum(u[key] for u in usage) for key in
              ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "cost_usd")}
    model = next((u["model"] for u in reversed(usage) if u["model"]), settings.model)
    latency = round((time.perf_counter() - started) * 1000, 1)
    yield "done", {"model": model, **totals, "latency_ms": latency, "requests": len(usage), "stop": stop}
