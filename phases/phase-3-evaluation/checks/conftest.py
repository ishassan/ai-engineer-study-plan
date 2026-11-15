"""Fixtures of the Phase 3 checks.

The checks of this phase read your Postgres database, call the two model services of
Phase 2, and read your traces back from Langfuse through its public API. They use the fake
Claude API of the lab, so they make no request to a paid service.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

REPO = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_URL = "postgresql://assistant:assistant@localhost:5432/assistant"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def sql() -> Callable[..., list[dict[str, Any]]]:
    """A function that runs one SQL statement and returns the rows as dicts."""

    def run(statement: str, params: Any = ()) -> list[dict[str, Any]]:
        url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        try:
            with psycopg.connect(url, row_factory=dict_row, connect_timeout=3) as connection:
                cursor = connection.execute(statement, params)
                return cursor.fetchall() if cursor.description else []
        except psycopg.OperationalError as error:
            pytest.fail(f"Postgres is not ready. Run `make up` first.\n{error}", pytrace=False)

    return run


@pytest.fixture(scope="session")
def services() -> None:
    """Fail with a clear message when a model service of Phase 2 does not answer."""
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


class LangfuseAPI:
    """A small client of the Langfuse public API, for the checks."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000").rstrip("/")
        self.auth = (os.environ.get("LANGFUSE_PUBLIC_KEY", ""), os.environ.get("LANGFUSE_SECRET_KEY", ""))

    def get(self, path: str, **params: Any) -> Any:
        response = httpx.get(f"{self.base_url}{path}", params=params, auth=self.auth, timeout=10)
        response.raise_for_status()
        return response.json()

    def observations(self, since: datetime, **params: Any) -> list[dict[str, Any]]:
        """All observations that started after `since`, with their I/O, model and usage."""
        found, cursor = [], None
        while True:
            page = self.get(
                "/api/public/v2/observations",
                fromStartTime=since.isoformat(),
                toStartTime=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                fields="core,basic,io,model,usage",
                limit=1000,
                **({"cursor": cursor} if cursor else {}),
                **params,
            )
            found.extend(page["data"])
            cursor = (page.get("meta") or {}).get("cursor")
            if not cursor:
                return found

    def wait_for(
        self, since: datetime, ready: Callable[[list[dict[str, Any]]], bool], timeout: float = 60
    ) -> list[dict[str, Any]]:
        """Flush the traces of this process, then poll until `ready` is true or the time is over.

        Langfuse stores what it receives a few seconds later, so the checks wait for it.
        """
        from langfuse import get_client

        get_client().flush()
        deadline = time.monotonic() + timeout
        observations = self.observations(since)
        while not ready(observations) and time.monotonic() < deadline:
            time.sleep(1)
            observations = self.observations(since)
        time.sleep(2)  # Late observations of the same request.
        return self.observations(since)


@pytest.fixture(scope="session")
def langfuse() -> LangfuseAPI:
    """The Langfuse public API. Fail with a clear message when Langfuse does not run."""
    api = LangfuseAPI()
    if not all(api.auth):
        pytest.fail(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not set. Copy the Phase 3 lines of "
            ".env.example into .env.",
            pytrace=False,
        )
    try:
        api.get("/api/public/projects")
    except httpx.HTTPStatusError as error:
        pytest.fail(
            f"Langfuse does not accept the keys in .env ({error.response.status_code}). Use the keys "
            "of .env.example, or the keys of your project in the Langfuse UI.",
            pytrace=False,
        )
    except httpx.HTTPError as error:
        pytest.fail(
            f"Langfuse does not answer on {api.base_url}. Run `make up` and wait until "
            f"langfuse-web is healthy.\n{type(error).__name__}: {error}",
            pytrace=False,
        )
    return api


@pytest.fixture(scope="session")
def testset() -> list[dict[str, Any]]:
    path = REPO / "evals" / "testset.jsonl"
    assert path.exists(), "evals/testset.jsonl does not exist. Run `make start PHASE=3` first."
    return read_jsonl(path)
