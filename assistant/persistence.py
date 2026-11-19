"""Reference solution: the Postgres pool, the checkpointer and the store."""

from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from assistant.config import get_settings
from assistant.embeddings import embed
from assistant.ingest import normalise_arabic


@lru_cache
def _pool(url: str) -> ConnectionPool:
    # The checkpointer and the store need these three settings (see PostgresSaver.from_conn_string).
    return ConnectionPool(url, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                          min_size=1, max_size=8, timeout=10, open=True)


@lru_cache
def _checkpointer(url: str) -> PostgresSaver:
    saver = PostgresSaver(_pool(url))
    saver.setup()
    return saver


def _embed(texts: list[str]) -> list[list[float]]:
    return embed([normalise_arabic(text) for text in texts])


@lru_cache
def _store(url: str) -> PostgresStore:
    store = PostgresStore(_pool(url), index={"dims": 1024, "embed": _embed, "fields": ["text"]})
    store.setup()
    return store


def checkpointer() -> PostgresSaver:
    return _checkpointer(get_settings().database_url)


def store() -> PostgresStore:
    return _store(get_settings().database_url)
