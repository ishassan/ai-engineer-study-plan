"""Reference solution: the hand-written loop with memory and a planner."""

from __future__ import annotations

import json
from typing import Any, Iterator

import psycopg
from anthropic import transform_schema
from langfuse import get_client, observe
from pydantic import ValidationError

from assistant import conversations, memory, planner
from assistant.config import get_settings
from assistant.llm import stream_claude
from assistant.schemas import Answer
from assistant.tools import TOOLS, run_tool

SYSTEM_PROMPT = """\
You are the assistant of a data platform. You answer questions about the datasets in its \
catalogue. The catalogue holds public datasets about Saudi Arabia from these owners: the \
General Authority for Statistics, the Saudi Central Bank (SAMA), the Electricity and \
Cogeneration Regulatory Authority, the Transport General Authority, the Ministry of \
Environment, Water and Agriculture, Saudi Open Data, and the King Abdullah Petroleum Studies \
and Research Center. The themes of the catalogue are: Buildings, Climate & Sustainability, \
Conventional Fuels, Economy, Electricity, Industry, Renewable & Other Fuels, Transport, and \
Water & Agriculture.

How to work:
- You know nothing about the catalogue except what the tools return. Always search before you \
answer, also when you think that you know the answer.
- Search with a few keywords. If a search returns nothing useful, search again with other \
words: a synonym, a wider term, or the name of the owner. Make at most four searches for one \
question.
- When the question is about the content of a dataset (its fields, its columns, what it \
measures), get the schema of the dataset before you answer.
- When the question is about the size, the last update, the update frequency, the license or \
the owner of a dataset, get the stats of the dataset before you answer.
- When several datasets fit the question, name each of them. Do not choose only one.
- When a tool returns an error, read the message, correct the input and try again one time.
- When no dataset fits the question, say that the catalogue has no dataset for it. Do not \
invent a dataset, an id, a column or a number.
- When the question is about how a statistic is made (a definition, a data source, a sample, a \
base year, a unit, a reference period), search the documents with search_documents. Answer only \
from the passages that it returns.

How to answer:
- Give a short answer in plain text: two to four sentences. Name each dataset by its title.
- In dataset_ids, list the id of each dataset that the answer uses. Copy each id exactly as \
the tool returned it. List only datasets that answer the question, and not each search result.
- In tools_called, list the name of each tool that you called, one time each.
- In citations, give one item for each passage that supports the answer: the title of the \
document, the page and the chunk_id. Copy the three values exactly from the result of \
search_documents. Never cite a chunk_id that search_documents did not return in this conversation.
- Answer in the language of the question.
- When the user tells you a fact about themselves or their work that will help later answers, \
save it with save_memory.
"""


def build_request(messages: list[dict[str, Any]], facts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    settings = get_settings()
    system: list[dict[str, Any]] = [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
    ]
    if facts:
        # After the cached block, so the cache of the system prompt still works.
        system.append({"type": "text", "text": memory.facts_block(facts)})
    return {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "tools": TOOLS,
        "system": system,
        "output_config": {"format": {"type": "json_schema", "schema": transform_schema(Answer)}},
        "messages": messages,
    }


def returned_chunk_ids(output: str) -> set[str]:
    """The chunk ids in one result of search_documents."""
    try:
        rows = json.loads(output)
    except json.JSONDecodeError:
        return set()
    return {row["chunk_id"] for row in rows if isinstance(row, dict) and "chunk_id" in row}


def _add(totals: dict[str, Any], result: Any) -> None:
    usage = result.message.usage
    totals["input_tokens"] += usage.input_tokens
    totals["output_tokens"] += usage.output_tokens
    totals["cache_creation_input_tokens"] += usage.cache_creation_input_tokens or 0
    totals["cache_read_input_tokens"] += usage.cache_read_input_tokens or 0
    totals["cost_usd"] += result.cost_usd
    totals["latency_ms"] += result.latency_ms


# observe() keeps the trace open across the yields of the generator. Starlette runs each
# step of a streaming response in a worker thread, so a plain `with` block around the loop
# would lose the current span after the first yield.
@observe(name="ask", as_type="agent")
def answer_events(
    question: str, conversation_id: str | None = None, user: str = "anonymous"
) -> Iterator[tuple[str, dict[str, Any]]]:
    settings = get_settings()
    history: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    try:
        if conversation_id:
            conversations.open_conversation(conversation_id, user)
            history = conversations.load_context(conversation_id)
        facts = memory.search_facts(user, question)
    except psycopg.OperationalError:
        # Without the database the agent still answers, without history and memory.
        conversation_id = None
    turn: list[dict[str, Any]] = [{"role": "user", "content": question}]
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_usd": 0.0,
        "latency_ms": 0.0,
    }
    requests = 0
    stop = "max_turns"
    model = settings.model
    known_chunk_ids: set[str] = set()
    retried = False
    plan = None
    if settings.planner:
        plan, result = planner.write_plan(question)
        requests += 1
        _add(totals, result)
        yield "plan", {"steps": plan.steps}
        turn[0]["content"] = f"{question}\n\nFollow this plan:\n{planner.numbered(plan)}"
    last_usage = None
    for _ in range(settings.max_turns):
        text = ""
        for kind, value in stream_claude(build_request(history + turn, facts)):
            if kind == "text":
                text += value
            else:
                result = value
        message = result.message
        requests += 1
        model = message.model
        last_usage = message.usage
        _add(totals, result)
        if message.stop_reason == "tool_use":
            turn.append({"role": "assistant", "content": message.content})
            results: list[dict[str, Any]] = []
            failed = None
            for block in message.content:
                if block.type != "tool_use":
                    continue
                with get_client().start_as_current_observation(
                    as_type="tool", name=block.name, input=block.input
                ) as span:
                    try:
                        output, is_error = run_tool(block.name, block.input, user, conversation_id), False
                        span.update(output=output)
                    except Exception as error:
                        output, is_error = f"{type(error).__name__}: {error}", True
                        span.update(output=output, level="ERROR", status_message=output)
                        failed = failed or (block.name, block.input, output)
                if block.name == "search_documents" and not is_error:
                    known_chunk_ids |= returned_chunk_ids(output)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                        "is_error": is_error,
                    }
                )
                yield "tool", {"name": block.name, "input": block.input, "is_error": is_error}
            if plan is not None and failed is not None:
                # The step failed: the model changes the plan, and the loop goes on with it.
                plan, plan_result = planner.change_plan(question, plan, *failed)
                requests += 1
                _add(totals, plan_result)
                yield "plan", {"steps": plan.steps}
                results.append(
                    {"type": "text", "text": f"A step failed. Follow the new plan:\n{planner.numbered(plan)}"}
                )
            turn.append({"role": "user", "content": results})
            continue
        stop = "final"
        turn.append({"role": "assistant", "content": message.content})
        if message.stop_reason != "end_turn":
            yield "error", {"message": f"The model stopped with {message.stop_reason}."}
            break
        try:
            answer = Answer.model_validate_json(text)
        except ValidationError as error:
            yield "error", {"message": f"The answer is not valid: {error.errors()[0]['msg']}"}
            break
        wrong = sorted({c.chunk_id for c in answer.citations} - known_chunk_ids)
        if wrong and not retried:
            # Reject the answer: keep it in the conversation, name the wrong ids, and ask again.
            retried = True
            stop = "max_turns"
            turn.append(
                {
                    "role": "user",
                    "content": (
                        "Your answer cites chunk ids that search_documents did not return in this "
                        f"conversation: {', '.join(wrong)}. Give the answer again. Cite only chunk "
                        "ids from the tool results, or search again first."
                    ),
                }
            )
            continue
        if wrong:
            yield "error", {"message": f"The answer cites unknown chunk ids: {', '.join(wrong)}"}
            break
        yield "answer", answer.model_dump()
        break
    if stop == "max_turns":
        yield "error", {"message": f"No final answer after {settings.max_turns} turns."}
    if conversation_id:
        if turn[-1]["role"] == "user":
            # The loop stopped after tool results: close the turn, so the next one starts right.
            turn.append({"role": "assistant", "content": "I could not finish the answer."})
        conversations.append_messages(conversation_id, turn)
        if last_usage is not None and memory.context_tokens(last_usage) >= settings.compact_at_tokens:
            new_context, summary_result = memory.compact(history + turn)
            requests += 1
            _add(totals, summary_result)
            conversations.start_new_context(conversation_id, new_context)
    yield "done", {"model": model, **totals, "requests": requests, "stop": stop}
