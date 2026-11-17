"""Fixtures of the Phase 6 checks.

Most checks of this phase send the model calls of your code through a LiteLLM gateway with your
gateway/config.yaml (the fixture `gateway` of labkit). The providers of that gateway are the
fake Claude API and the fake OpenAI API of the lab, and the fake OpenAI API also stands in for
vLLM on your pod. So the checks need Docker and Postgres (`make up`), but no GPU, no key and no
paid request.

The checks start your two MCP servers from assistant/servers/ for the whole run, as in Phases 4
and 5, because the graph gets most of its tools from them.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from labkit.processes import McpServer, start_servers


@pytest.fixture(scope="session", autouse=True)
def mcp_servers() -> Iterator[dict[str, McpServer]]:
    """Start both MCP servers of assistant/servers/ for the whole run."""
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
