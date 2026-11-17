"""Run the two MCP servers of assistant/servers/ as processes, for the attack suite and the checks.

From Phase 4, week 16, the graph gets most of its tools from these servers. The attack suite
and the Phase 5 checks start both servers from your code on free ports, so they always test
your current code. The Compose services of `make up` can run at the same time.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVERS = {
    "sql": ("assistant.servers.sql_server", "MCP_SQL_URL"),
    "catalogue": ("assistant.servers.catalogue_server", "MCP_CATALOGUE_URL"),
}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_port(process: subprocess.Popen, port: int, seconds: float) -> bool:
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

    def __init__(self, name: str, module: str, folder: Path, settings: dict[str, str] | None = None) -> None:
        self.name, self.module, self.settings = name, module, settings or {}
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self.log = folder / f"mcp-{name}.log"
        self.log.write_text("")
        self.start()

    def start(self) -> None:
        self.error = None
        env = dict(os.environ, MCP_HOST="127.0.0.1", MCP_PORT=str(self.port), **self.settings)
        with open(self.log, "a") as output:
            self.process = subprocess.Popen([sys.executable, "-m", self.module], cwd=REPO, env=env,
                                            stdout=output, stderr=subprocess.STDOUT)
        if not wait_for_port(self.process, self.port, 60):
            self.error = f"The server {self.module} did not start.\n{self.output()[-2000:]}"

    def output(self) -> str:
        return self.log.read_text(errors="replace") if self.log.exists() else ""

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def start_servers(folder: Path, settings: dict[str, str] | None = None) -> dict[str, McpServer]:
    """Start both servers when assistant/servers/ exists, and point the MCP settings at them."""
    servers: dict[str, McpServer] = {}
    if (REPO / "assistant" / "servers" / "sql_server.py").exists():
        for name, (module, variable) in SERVERS.items():
            servers[name] = McpServer(name, module, folder, settings)
            os.environ[variable] = servers[name].url
    return servers
