"""Fixtures of the Phase 4 checks.

The checks of this phase read your Postgres database and call the embedding service of
Phase 2 (the memory search) and, for the document search, the re-ranking service. The
model is the fake Claude API or the fake OpenAI API of the lab, so the checks make no
request to a paid service.

From week 16 the graph gets most tools from your two MCP servers. The checks start the two
servers from your code (assistant/servers/) on free ports for the whole run, and set
MCP_SQL_URL and MCP_CATALOGUE_URL to them. So a check always tests your current code, and
the Compose services of `make up` can run at the same time.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

try:
    from labkit.auth import SignedInClient
except ImportError:  # PyJWT is not installed: no sign-in before Phase 5.
    SignedInClient = httpx.Client  # type: ignore[assignment,misc]

DEFAULT_DATABASE_URL = "postgresql://assistant:assistant@localhost:5432/assistant"
REPO = Path(__file__).resolve().parents[3]


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


@pytest.fixture
def tables(sql) -> None:
    """Fail with a clear message when the migration of week 12 did not run."""
    found = {row["table_name"] for row in sql(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )}
    missing = {"conversations", "conversation_messages", "memories"} - found
    if missing:
        pytest.fail(
            f"The tables {', '.join(sorted(missing))} do not exist. Run `make up`: it applies "
            "db/migrations/0005_conversations_and_memory.sql.",
            pytrace=False,
        )


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
def embeddings() -> None:
    """Fail with a clear message when the embedding service does not answer."""
    _service("embeddings", "EMBEDDINGS_URL", "http://localhost:8081")


@pytest.fixture(scope="session")
def services(embeddings) -> None:
    """Fail with a clear message when a model service of Phase 2 does not answer."""
    _service("reranker", "RERANKER_URL", "http://localhost:8082")


# ---- processes: the MCP servers and the API -------------------------------------------------

# The settings of the SQL server in the checks. They are small, so the checks are fast.
SERVER_SETTINGS = {"SQL_ROW_LIMIT": "40", "SQL_TIMEOUT_SECONDS": "2"}
SERVERS = {
    "sql": ("assistant.servers.sql_server", "MCP_SQL_URL"),
    "catalogue": ("assistant.servers.catalogue_server", "MCP_CATALOGUE_URL"),
}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_for_port(process: subprocess.Popen, port: int, seconds: float) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end and process.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class McpServer:
    """One MCP server of your code, as a process. `log` holds its output."""

    def __init__(self, name: str, module: str, folder: Path) -> None:
        self.name, self.module = name, module
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self.log = folder / f"mcp-{name}.log"
        self.log.write_text("")
        self.start()

    def start(self) -> None:
        """Start the server on its port. The log keeps the output of each start."""
        self.error = None
        env = dict(os.environ, MCP_HOST="127.0.0.1", MCP_PORT=str(self.port), **SERVER_SETTINGS)
        with open(self.log, "a") as output:
            self.process = subprocess.Popen([sys.executable, "-m", self.module], cwd=REPO, env=env,
                                            stdout=output, stderr=subprocess.STDOUT)
        if not _wait_for_port(self.process, self.port, 60):
            self.error = f"The server {self.module} did not start.\n{self.output()[-2000:]}"

    def output(self) -> str:
        return self.log.read_text(errors="replace") if self.log.exists() else ""

    def tool_calls(self) -> int:
        """The number of tool calls that the server logged (the SDK logs each request type)."""
        return self.output().count("CallToolRequest")

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()


@pytest.fixture(scope="session", autouse=True)
def mcp_servers() -> Iterator[dict[str, McpServer]]:
    """Start both MCP servers of assistant/servers/ for the whole run (week 16)."""
    folder = Path(tempfile.mkdtemp(prefix="lab-mcp-"))
    servers: dict[str, McpServer] = {}
    if (REPO / "assistant" / "servers" / "sql_server.py").exists():
        for name, (module, variable) in SERVERS.items():
            servers[name] = McpServer(name, module, folder)
            os.environ[variable] = servers[name].url
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


class Service:
    """Your API (assistant/api.py) as a real process, with uvicorn, against the fake APIs."""

    def __init__(self, folder: Path, env: dict[str, str]) -> None:
        self.folder, self.env = folder, env
        self.process: subprocess.Popen | None = None
        self.client: httpx.Client | None = None
        self.starts = 0

    def start(self) -> None:
        port = free_port()
        self.starts += 1
        log = self.folder / f"api-{self.starts}.log"
        with open(log, "w") as output:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "assistant.api:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=REPO, env=self.env, stdout=output, stderr=subprocess.STDOUT,
            )
        if not _wait_for_port(self.process, port, 90):
            self.kill()
            pytest.fail(f"The API did not start with uvicorn.\n{log.read_text(errors='replace')[-3000:]}", pytrace=False)
        # From Phase 5 the API needs a token: the client signs in each request (labkit/auth.py).
        self.client = SignedInClient(base_url=f"http://127.0.0.1:{port}", timeout=180)

    def kill(self) -> None:
        """Stop the process at once (SIGKILL), as a crash does: no code of the service runs."""
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(10)


@pytest.fixture
def service(tmp_path) -> Iterator[Service]:
    """Your API as a process with the graph (AGENT_IMPL=langgraph). Call start() and kill()."""
    env = dict(os.environ, AGENT_IMPL="langgraph", AGENT_PLANNER="off", PROVIDER="anthropic")
    running = Service(tmp_path, env)
    yield running
    running.kill()
