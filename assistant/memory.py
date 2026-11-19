"""Reference solution: compaction, and the long-term memory in the LangGraph store."""

from __future__ import annotations

import json
import uuid
from typing import Any

from assistant.config import get_settings
from assistant.llm import call_claude
from assistant.persistence import store

SUMMARY_PROMPT = """\
You write the summary of a conversation between a user and the assistant of a data \
platform. A new context starts with your summary, and the assistant does not see the old \
messages again. Keep each fact that a later answer can need: the questions of the user, the \
id and title of each dataset that the answers named, the chunk ids of cited passages, the \
decisions and the open questions. Leave out the raw tool results. Write plain text, at most \
300 words.\
"""

SUMMARY_PREFIX = "Summary of the conversation so far (the older messages were compacted):"


def context_tokens(usage: Any) -> int:
    """The size of the context after a reply: the whole prompt plus the reply."""
    return (
        usage.input_tokens
        + (usage.cache_creation_input_tokens or 0)
        + (usage.cache_read_input_tokens or 0)
        + usage.output_tokens
    )


def _block_text(block: dict[str, Any]) -> str:
    kind = block.get("type")
    if kind == "text":
        return block.get("text", "")
    if kind == "tool_use":
        return f"[tool call {block.get('name')} {json.dumps(block.get('input'), ensure_ascii=False)}]"
    if kind == "tool_result":
        content = block.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        return f"[tool result {text[:300]}]"
    return ""


def transcript(messages: list[dict[str, Any]]) -> str:
    """The conversation as plain text, for the summary request."""
    lines = []
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            text = content
        else:
            blocks = [b if isinstance(b, dict) else b.model_dump(mode="json") for b in content]
            text = " ".join(filter(None, (_block_text(block) for block in blocks)))
        if text:
            lines.append(f"{message['role']}: {text}")
    return "\n".join(lines)


def compact(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Any]:
    """Summarise the messages. Return the messages of the new context and the model result."""
    settings = get_settings()
    request = {
        "model": settings.model,
        "max_tokens": 1024,
        "system": SUMMARY_PROMPT,
        "messages": [{"role": "user", "content": transcript(messages)}],
    }
    result = call_claude(request)
    summary = "".join(block.text for block in result.message.content if block.type == "text")
    return [{"role": "user", "content": f"{SUMMARY_PREFIX}\n{summary}"},
            {"role": "assistant", "content": "I will use this summary in the rest of the conversation."}], result


def _namespace(user: str) -> tuple[str, ...]:
    # A label of a namespace cannot hold a period, and a user name can (an e-mail address).
    return ("memories", user.replace("%", "%25").replace(".", "%2E"))


def save_fact(user: str, fact: str, conversation_id: str | None = None) -> str:
    key = uuid.uuid4().hex
    store().put(_namespace(user), key, {"text": fact, "conversation_id": conversation_id})
    return key


def search_facts(user: str, text: str, k: int | None = None) -> list[dict[str, Any]]:
    """The saved facts of the user that are closest to the text, best first."""
    if not store().search(_namespace(user), limit=1):
        return []
    k = k or get_settings().memory_results
    items = store().search(_namespace(user), query=text, limit=k)
    return [{"id": item.key, "text": item.value["text"], "score": item.score} for item in items]


def facts_block(facts: list[dict[str, Any]]) -> str:
    lines = "\n".join(f"- {fact['text']}" for fact in facts)
    return (
        "Facts that you saved about this user in earlier conversations (use them when they "
        f"help; they can be old):\n{lines}"
    )
