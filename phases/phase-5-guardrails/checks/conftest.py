"""Fixtures of the Phase 5 checks.

The checks of this phase read your Postgres database, call both model services of Phase 2 (the
document search) and, in week 20, the NeMo Guardrails server. The model is the fake Claude API
of the lab, also in its obedient form (labkit/obedient.py), so the checks make no request to a
paid service. The sign-in uses the fake authorization server of labkit (labkit/auth.py): it
gives tokens with the same claims as the realm `lab` of Keycloak.

The checks start your two MCP servers from assistant/servers/ on free ports for the whole run,
as in Phase 4, and set MCP_SQL_URL and MCP_CATALOGUE_URL to them.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from labkit.processes import McpServer, start_servers

DEFAULT_DATABASE_URL = "postgresql://assistant:assistant@localhost:5432/assistant"
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def sql() -> Callable[..., list[dict[str, Any]]]:
    """A function that runs one SQL statement as the owner of the tables and returns the rows."""

    def run(statement: str, params: Any = ()) -> list[dict[str, Any]]:
        url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        try:
            with psycopg.connect(url, row_factory=dict_row, connect_timeout=3) as connection:
                cursor = connection.execute(statement, params)
                return cursor.fetchall() if cursor.description else []
        except psycopg.OperationalError as error:
            pytest.fail(f"Postgres is not ready. Run `make up` first.\n{error}", pytrace=False)

    return run


def _service(name: str, variable: str, default: str) -> None:
    url = os.environ.get(variable, default).rstrip("/")
    try:
        httpx.get(f"{url}/health", timeout=5).raise_for_status()
    except httpx.HTTPError as error:
        pytest.fail(
            f"The service `{name}` does not answer on {url}. Run `make up` and wait until "
            f"the model is loaded.\n{type(error).__name__}: {error}",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def services() -> None:
    """Fail with a clear message when a model service of Phase 2 does not answer."""
    _service("embeddings", "EMBEDDINGS_URL", "http://localhost:8081")
    _service("reranker", "RERANKER_URL", "http://localhost:8082")


@pytest.fixture(scope="session", autouse=True)
def mcp_servers() -> Iterator[dict[str, McpServer]]:
    """Start both MCP servers of assistant/servers/ for the whole run."""
    servers = start_servers(Path(tempfile.mkdtemp(prefix="lab-mcp-")))
    yield servers
    for server in servers.values():
        server.stop()


@pytest.fixture
def mcp(mcp_servers) -> dict[str, McpServer]:
    """The two MCP servers. Fail with a clear message when one did not start."""
    if not mcp_servers:
        pytest.fail("assistant/servers/ does not exist. Run `make start PHASE=4`.", pytrace=False)
    for server in mcp_servers.values():
        if server.error:
            pytest.fail(server.error, pytrace=False)
    return mcp_servers


@pytest.fixture
def graph(monkeypatch) -> None:
    """Run the API with the graph, which asks for approval (Phase 4, week 15)."""
    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("AGENT_PLANNER", "off")
