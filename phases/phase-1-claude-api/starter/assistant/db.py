"""Access to Postgres. Use query() for each read of the catalogue."""

from __future__ import annotations

from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

from assistant.config import get_settings


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
