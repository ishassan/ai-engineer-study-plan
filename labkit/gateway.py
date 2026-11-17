"""A LiteLLM gateway for the offline checks of Phase 6, with the fake APIs as its providers.

The checks of Phase 6 test your gateway configuration (gateway/config.yaml) and your code
together. This module starts one more container of the Compose service `gateway`, with the same
image and your configuration, but with other settings:

- The providers are the fake Claude API and the fake OpenAI API of the checks. The fake OpenAI
  API also stands in for vLLM on your pod. Each provider gets a key that only the checks use, so
  a check can see that a request came through the gateway and not directly from your code.
- The gateway keeps its spend and budgets in a database of its own (`litellm_checks_<process
  id>`), so the checks never change the budgets and the spend of your own gateway. Each run
  starts with an empty database and deletes it at the end.
  When your configuration names a default budget for each user (max_end_user_budget_id), the
  module creates that budget with CHECK_BUDGET_USD, so the checks can spend it on purpose.
- The admin key is MASTER_KEY.

The container runs in Docker and the fake APIs run in the process of pytest, so the module also
serves each fake API on all network interfaces of your machine (a relay, with the same state as
the fake). The container reaches them at host.docker.internal.

Your code calls the gateway through one more relay on 127.0.0.1 (the address in GATEWAY_URL).
That relay keeps the User-Agent of the last request, and the relays of the fake APIs give it to
the fake API in place of the User-Agent of the gateway (the one of the gateway goes in the header
x-gateway-user-agent). So a check of an earlier phase that reads the User-Agent still sees which
client library (the anthropic SDK or LangChain) made the call. The checks send one question at a
time, so the last User-Agent is the one of the call that the fake API gets.

`pytest --gateway` sends the model calls of all offline checks through this gateway.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "gateway" / "config.yaml"
MASTER_KEY = "sk-lab-check-master"
DATABASE = "litellm_checks"
UPSTREAM_KEYS = {
    "anthropic": "check-upstream-anthropic-key",
    "openai": "check-upstream-openai-key",
    "vllm": "check-upstream-vllm-key",
}
START_SECONDS = 240
CHECK_BUDGET_USD = 1000.0


def _free_port(host: str = "127.0.0.1") -> int:
    with socket.socket() as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


class ClientAgent:
    """The User-Agent of the last request from your code to the gateway."""

    def __init__(self) -> None:
        self.value: str | None = None


class Relay:
    """Serve an app on a free port. The default host (all interfaces) lets a container reach it."""

    def __init__(self, app: Any, host: str = "0.0.0.0") -> None:
        self.port = _free_port(host)
        config = uvicorn.Config(app, host=host, port=self.port, log_level="error", lifespan="off")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started and time.monotonic() < deadline:
            time.sleep(0.02)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


def with_client_agent(app: Any, agent: ClientAgent) -> Any:
    """Wrap the app of a fake API: give it the User-Agent of your code, not the one of the gateway."""

    async def wrapped(scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and agent.value:
            gateway_agent = dict(scope["headers"]).get(b"user-agent", b"")
            headers = [(name, value) for name, value in scope["headers"] if name != b"user-agent"]
            headers += [(b"user-agent", agent.value.encode("latin-1")), (b"x-gateway-user-agent", gateway_agent)]
            scope = {**scope, "headers": headers}
        await app(scope, receive, send)

    return wrapped


# Headers that belong to one connection. The front relay does not copy them.
HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "keep-alive"}


def front_app(target: str, agent: ClientAgent) -> Any:
    """An app that sends each request to the gateway at `target` and streams the answer back.
    It keeps the User-Agent of each request in `agent`."""
    import httpx

    clients: list[httpx.AsyncClient] = []

    async def app(scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        if not clients:  # made in the event loop of the relay
            clients.append(httpx.AsyncClient(base_url=target, timeout=httpx.Timeout(600.0)))
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        headers = [(name.decode("latin-1"), value.decode("latin-1")) for name, value in scope["headers"]
                   if name.decode("latin-1").lower() not in HOP_HEADERS]
        agent.value = next((value for name, value in headers if name.lower() == "user-agent"), None) or agent.value
        path = scope["raw_path"].decode("latin-1") if scope.get("raw_path") else scope["path"]
        if scope.get("query_string") and "?" not in path:
            path += "?" + scope["query_string"].decode("latin-1")
        request = clients[0].build_request(scope["method"], path, headers=headers, content=body)
        try:
            response = await clients[0].send(request, stream=True)
        except httpx.HTTPError as error:
            text = f"The check relay could not reach the gateway: {error}".encode()
            await send({"type": "http.response.start", "status": 502,
                        "headers": [(b"content-type", b"text/plain"), (b"content-length", str(len(text)).encode())]})
            await send({"type": "http.response.body", "body": text})
            return
        try:
            await send({"type": "http.response.start", "status": response.status_code, "headers": [
                (name.encode("latin-1"), value.encode("latin-1")) for name, value in response.headers.multi_items()
                if name.lower() not in HOP_HEADERS]})
            async for chunk in response.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            await response.aclose()

    return app


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://assistant:assistant@localhost:5432/assistant")


def create_database(name: str) -> None:
    """Create an empty database for the check gateway. Delete the databases of earlier runs that ended
    without their clean-up (a database that a running gateway uses cannot be deleted, so it stays)."""
    import psycopg

    with psycopg.connect(_database_url(), autocommit=True, connect_timeout=5) as connection:
        old = connection.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", (f"{DATABASE}%",)).fetchall()
        for (database,) in old:
            try:
                connection.execute(f'DROP DATABASE IF EXISTS "{database}"')
            except psycopg.Error:
                pass
        connection.execute(f'CREATE DATABASE "{name}"')


def drop_database(name: str) -> None:
    import psycopg

    try:
        with psycopg.connect(_database_url(), autocommit=True, connect_timeout=5) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    except psycopg.Error:
        pass


def default_budget_id() -> str | None:
    """The budget that your configuration gives each user (litellm_settings.max_end_user_budget_id)."""
    import yaml

    try:
        config = yaml.safe_load(CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    return ((config.get("litellm_settings") or {}).get("max_end_user_budget_id")) or None


class CheckGateway:
    """One container of the service `gateway` for a run of the checks."""

    def __init__(self, fake_claude: Any, fake_openai: Any) -> None:
        self.fake_claude, self.fake_openai = fake_claude, fake_openai
        self.name = f"assistant-gateway-check-{os.getpid()}"
        self.database = f"{DATABASE}_{os.getpid()}"
        # start() chooses the port of the gateway. The admin API (the checks) calls the gateway
        # directly at `direct_url`; your code calls it through the front relay at `url`.
        self.port = 0
        self.direct_url = self.url = ""
        self.agent = ClientAgent()
        self.error: str | None = None
        self.relays: list[Relay] = []
        self.started = False

    # ---- start and stop ---------------------------------------------------------------------

    def start(self) -> None:
        self.started = True
        if not CONFIG.exists():
            self.error = "gateway/config.yaml does not exist. Run `make start PHASE=6` first."
            return
        try:
            create_database(self.database)
        except Exception as error:  # noqa: BLE001 - any failure here means Postgres is not ready
            self.error = f"Postgres is not ready. Run `make up` first.\n{type(error).__name__}: {error}"
            return
        claude = Relay(with_client_agent(self.fake_claude.app(), self.agent))
        openai = Relay(with_client_agent(self.fake_openai.app(), self.agent))
        self.relays = [claude, openai]
        # Choose the port after the relays hold theirs. A port that was free a moment ago can be
        # given again to the next socket, and then Docker cannot bind it.
        self.port = _free_port()
        self.direct_url = self.url = f"http://127.0.0.1:{self.port}"
        host = "http://host.docker.internal"
        settings = {
            "DATABASE_URL": f"postgresql://assistant:assistant@db:5432/{self.database}",
            "LITELLM_MASTER_KEY": MASTER_KEY,
            "ANTHROPIC_API_KEY": UPSTREAM_KEYS["anthropic"],
            "ANTHROPIC_API_BASE": f"{host}:{claude.port}",
            "OPENAI_API_KEY": UPSTREAM_KEYS["openai"],
            "OPENAI_API_BASE": f"{host}:{openai.port}/v1",
            "VLLM_API_BASE": f"{host}:{openai.port}/v1",
            "VLLM_API_KEY": UPSTREAM_KEYS["vllm"],
        }
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
        # --no-deps: the database exists already (create_database above), and two runs of the checks
        # at the same time must not both start the one-shot service gateway-db.
        command = ["docker", "compose", "-f", str(REPO / "compose.yaml"), "--profile", "phase6", "run",
                   "-d", "--rm", "--no-deps", "--name", self.name, "-p", f"127.0.0.1:{self.port}:4000"]
        for name, value in settings.items():
            command += ["-e", f"{name}={value}"]
        command.append("gateway")
        try:
            result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as error:
            self.error = f"Docker did not start the gateway: {error}"
            return
        if result.returncode != 0:
            self.error = f"`docker compose run gateway` failed:\n{result.stderr[-3000:]}"
            return
        self._wait()
        if self.error is None:
            front = Relay(front_app(self.direct_url, self.agent), host="127.0.0.1")
            self.relays.append(front)
            self.url = f"http://127.0.0.1:{front.port}"
        name = default_budget_id()
        if self.error is None and name:
            status, body = self.admin("POST", "/budget/new", {"budget_id": name, "max_budget": CHECK_BUDGET_USD})
            if status != 200:
                self.error = f"The check could not create the budget `{name}` in the gateway: {status} {body}"

    def _wait(self) -> None:
        deadline = time.monotonic() + START_SECONDS
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{self.direct_url}/health/readiness", timeout=3) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                pass
            if not self.running():
                self.error = "The gateway stopped. Its last log lines:\n" + self.logs()
                return
            time.sleep(1)
        self.error = f"The gateway did not start in {START_SECONDS} s. Its last log lines:\n" + self.logs()

    def running(self) -> bool:
        result = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", self.name],
                                capture_output=True, text=True)
        return result.stdout.strip() == "true"

    def logs(self, lines: int = 60) -> str:
        result = subprocess.run(["docker", "logs", "--tail", str(lines), self.name], capture_output=True, text=True)
        return (result.stdout + result.stderr)[-6000:]

    def stop(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
        for relay in self.relays:
            relay.stop()
        if self.started:
            drop_database(self.database)

    # ---- the admin API ----------------------------------------------------------------------

    def admin(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        """Call the admin API with the master key. Return the status and the JSON body."""
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(f"{self.direct_url}{path}", data=data, method=method, headers={
            "Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            text = error.read().decode(errors="replace")
            try:
                return error.code, json.loads(text)
            except json.JSONDecodeError:
                return error.code, text
