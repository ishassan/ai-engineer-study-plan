"""Fixtures of the Phase 2 checks.

The checks of this phase read your Postgres database. From week 5 they also call
the embedding service and the re-ranking service on your machine (`make up`
starts them). They make no request to a paid service.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

REPO = Path(__file__).resolve().parents[3]
DEFAULT_URL = "postgresql://assistant:assistant@localhost:5432/assistant"


@pytest.fixture(scope="session")
def documents() -> list[dict[str, str]]:
    """The rows of data/documents.csv whose PDF file is in data/documents/."""
    with (REPO / "data" / "documents.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    fetched = [row for row in rows if (REPO / "data" / "documents" / f"{row['id']}.pdf").exists()]
    if len(fetched) < 0.9 * len(rows):
        pytest.fail(
            f"data/documents/ holds {len(fetched)} of the {len(rows)} documents. Run `make documents`.",
            pytrace=False,
        )
    return fetched


@pytest.fixture
def sql() -> Any:
    """A function that runs one SQL statement and returns the rows as dicts."""

    def run(statement: str, params: Any = ()) -> list[dict[str, Any]]:
        url = os.environ.get("DATABASE_URL", DEFAULT_URL)
        try:
            with psycopg.connect(url, row_factory=dict_row, connect_timeout=3) as connection:
                cursor = connection.execute(statement, params)
                return cursor.fetchall() if cursor.description else []
        except psycopg.OperationalError as error:
            pytest.fail(f"Postgres is not ready. Run `make up` first.\n{error}", pytrace=False)

    return run


@pytest.fixture
def chunks(sql) -> int:
    """Fail with a clear message when the table chunks is missing or empty."""
    try:
        count = sql("SELECT count(*) AS n FROM chunks")[0]["n"]
    except psycopg.errors.UndefinedTable:
        pytest.fail("The table chunks does not exist. Run `make up` to apply the migrations.", pytrace=False)
    if count == 0:
        pytest.fail("The table chunks is empty. Run `make ingest` (week 4, step 4).", pytrace=False)
    return count


@pytest.fixture(scope="session")
def services() -> None:
    """Fail with a clear message when a model service does not answer."""
    for name, variable, default in (
        ("embeddings", "EMBEDDINGS_URL", "http://localhost:8081"),
        ("reranker", "RERANKER_URL", "http://localhost:8082"),
    ):
        url = os.environ.get(variable, default).rstrip("/")
        try:
            httpx.get(f"{url}/health", timeout=5).raise_for_status()
        except httpx.HTTPError as error:
            pytest.fail(
                f"The service `{name}` does not answer on {url}. Run `make up` and wait until "
                f"the model is loaded.\n{type(error).__name__}: {error}",
                pytrace=False,
            )
