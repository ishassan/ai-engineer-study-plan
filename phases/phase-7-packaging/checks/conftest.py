"""Fixtures of the Phase 7 checks.

The checks of week 26 send questions to your API with the fake Claude API of the lab, and read
the traces and the scores back from your Langfuse through its public API. So they need Postgres
and Langfuse (`make up`), but no key and no paid request. The other checks read files: the
documents of docs/ and the result files of Phases 1 to 6 under evals/.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import pytest

from labkit.processes import McpServer, start_servers

REPO = Path(__file__).resolve().parents[3]


class LangfuseAPI:
    """A small client of the Langfuse public API: the observations of a trace and its scores."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000").rstrip("/")
        self.auth = (os.environ.get("LANGFUSE_PUBLIC_KEY", ""), os.environ.get("LANGFUSE_SECRET_KEY", ""))

    def get(self, path: str, **params: Any) -> Any:
        response = httpx.get(f"{self.base_url}{path}", params=params, auth=self.auth, timeout=10)
        response.raise_for_status()
        return response.json()

    def observations(self, trace_id: str) -> list[dict[str, Any]]:
        return self.get("/api/public/v2/observations", traceId=trace_id, fields="core,basic,io")["data"]

    def scores(self, trace_id: str) -> list[dict[str, Any]]:
        """The scores of a trace. Langfuse v4 serves them on /api/public/v3/scores."""
        return self.get("/api/public/v3/scores", traceId=trace_id, fields="core,details,subject")["data"]

    def wait_for(
        self,
        read: Callable[[], list[dict[str, Any]]],
        ready: Callable[[list[dict[str, Any]]], bool],
        timeout: float = 45,
    ) -> list[dict[str, Any]]:
        """Flush the traces and scores of this process, then poll until `ready` is true or the time is over.

        Langfuse stores what it receives a few seconds later, so the checks wait for it.
        """
        from langfuse import get_client

        get_client().flush()
        deadline = time.monotonic() + timeout
        found = read()
        while not ready(found) and time.monotonic() < deadline:
            time.sleep(1)
            found = read()
        return found


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
    except httpx.HTTPError as error:
        pytest.fail(
            f"Langfuse does not answer on {api.base_url} with the keys of .env. Run `make up` and "
            f"wait until langfuse-web is healthy.\n{type(error).__name__}: {error}",
            pytrace=False,
        )
    return api


@pytest.fixture(scope="session")
def mcp_servers() -> Iterator[dict[str, McpServer]]:
    """Start both MCP servers of assistant/servers/ for the checks that use the graph."""
    servers = start_servers(Path(tempfile.mkdtemp(prefix="lab-mcp-")))
    yield servers
    for server in servers.values():
        server.stop()


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch, mcp_servers: dict[str, McpServer]) -> None:
    """Run the API with the graph of Phase 4 (AGENT_IMPL=langgraph)."""
    for server in mcp_servers.values():
        if server.error:
            pytest.fail(server.error, pytrace=False)
    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("AGENT_PLANNER", "off")
    monkeypatch.setenv("PROVIDER", "anthropic")
