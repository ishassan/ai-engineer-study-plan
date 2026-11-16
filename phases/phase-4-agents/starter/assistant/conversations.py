"""The messages of each conversation, in Postgres. Week 12. This file is complete.

The tables come from db/migrations/0005_conversations_and_memory.sql. A conversation
belongs to one user. Its messages are in the format of the model API: each message is
a dict with `role` and `content`, as you send it in `messages`.

A conversation has one or more contexts. The agent reads only the messages of the last
context. Compaction (your work in memory.py) starts a new context with a summary, so the
model does not read the old messages again. The old messages stay in the table.

    open_conversation(conversation_id, user)   make the conversation, or check its user
    load_context(conversation_id)              the messages of the last context
    append_messages(conversation_id, messages) add messages to the last context
    start_new_context(conversation_id, messages)  compaction: a new context with these messages
"""

from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from assistant.db import connect


class ConversationNotFound(LookupError):
    """The conversation belongs to another user."""


def _plain(value: Any) -> Any:
    """Turn the SDK objects in a message (content blocks) into JSON values."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    raise TypeError(f"Cannot store a value of the type {type(value).__name__}.")


def _jsonable(content: Any) -> Any:
    return json.loads(json.dumps(content, default=_plain, ensure_ascii=False))


def open_conversation(conversation_id: str, user: str) -> bool:
    """Make the conversation for the user, or check that it is theirs.

    Returns True for a new conversation. Raises ConversationNotFound when the ID belongs
    to another user, so a user never reads the messages of another user.
    """
    with connect() as connection:
        row = connection.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s) "
            "ON CONFLICT (id) DO NOTHING RETURNING id",
            (conversation_id, user),
        ).fetchone()
        if row is not None:
            return True
        owner = connection.execute(
            "SELECT user_id FROM conversations WHERE id = %s", (conversation_id,)
        ).fetchone()
    if owner["user_id"] != user:
        raise ConversationNotFound(f"There is no conversation {conversation_id} for this user.")
    return False


def _last_context(connection: Any, conversation_id: str) -> int:
    row = connection.execute(
        "SELECT coalesce(max(context), 0) AS context FROM conversation_messages WHERE conversation_id = %s",
        (conversation_id,),
    ).fetchone()
    return row["context"]


def load_context(conversation_id: str) -> list[dict[str, Any]]:
    """The messages of the last context, in order, as dicts with `role` and `content`."""
    with connect() as connection:
        context = _last_context(connection, conversation_id)
        rows = connection.execute(
            "SELECT role, content FROM conversation_messages "
            "WHERE conversation_id = %s AND context = %s ORDER BY id",
            (conversation_id, context),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def _insert(connection: Any, conversation_id: str, context: int, messages: list[dict[str, Any]]) -> None:
    for message in messages:
        connection.execute(
            "INSERT INTO conversation_messages (conversation_id, context, role, content) "
            "VALUES (%s, %s, %s, %s)",
            (conversation_id, context, message["role"], Jsonb(_jsonable(message["content"]))),
        )


def append_messages(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    """Add messages at the end of the last context."""
    with connect() as connection:
        _insert(connection, conversation_id, _last_context(connection, conversation_id), messages)


def start_new_context(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    """Start a new context with these messages (for example, a summary of the old context)."""
    with connect() as connection:
        _insert(connection, conversation_id, _last_context(connection, conversation_id) + 1, messages)
