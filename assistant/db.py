"""Reference solution: access to Postgres, also with the rights of a user."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row

from assistant.config import get_settings

# The user of the current tool call. The graph sets it around a local tool (search_documents).
_identity: ContextVar[Any] = ContextVar("identity", default=None)
# The role of the queries that run with the rights of a user (migration 0010).
USER_ROLE = "assistant_retrieval"


def connect() -> psycopg.Connection:
    """Open a connection that returns each row as a dict."""
    return psycopg.connect(get_settings().database_url, row_factory=dict_row, connect_timeout=5)


def query(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[dict[str, Any]]:
    """Run one SELECT and return the rows.

    Always pass values through `params` (%s or %(name)s placeholders). Never put
    a value from the model into the SQL text.
    """
    with connect() as connection:
        return connection.execute(sql, params).fetchall()


@contextmanager
def as_identity(identity: Any) -> Iterator[None]:
    """Run the queries of query_as_user() in this block with the rights of `identity`."""
    token = _identity.set(identity)
    try:
        yield
    finally:
        _identity.reset(token)


def query_as_user(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[dict[str, Any]]:
    """Run one SELECT with the rights of the current user, so that row security applies.

    Without a user (a call from a script or a check), the session has no user and no group:
    it sees only the objects that have no rule.
    """
    identity = _identity.get()
    user = identity.user if identity is not None else ""
    groups = ",".join(identity.groups) if identity is not None else ""
    with connect() as connection:
        connection.execute("SELECT set_config('app.user', %s, true), set_config('app.groups', %s, true)", (user, groups))
        connection.execute(f"SET LOCAL ROLE {USER_ROLE}")
        return connection.execute(sql, params).fetchall()
