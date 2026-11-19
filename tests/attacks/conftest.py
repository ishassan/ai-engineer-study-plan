"""Fixtures of the attack suite, and the result file. Phase 5, week 18. This file is complete.

    make attacks LABEL=week18                  the real Claude API (costs money)
    make attacks LABEL=week18 MODEL=obedient   the obedient model of labkit (free, offline)

The suite needs Postgres with the documents and the poisoned material (`make poison`), and
both model services. It starts the two MCP servers of assistant/servers/ from your code, and it
runs your API in this process with the graph (AGENT_IMPL=langgraph), because only the graph
asks for approval. From week 20 the API calls the guardrails server: with MODEL=obedient the
suite uses it when it answers at GUARDRAILS_URL (default http://localhost:8100).

The obedient model (labkit/obedient.py) follows each instruction that it reads. A real model
ignores many attacks, so a pass can mean "the model was careful this time". With the obedient
model, a case passes only when a defence in the design stops the attack.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

import pytest

from evals.attacks import write_results

_rows: list[dict[str, Any]] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("attacks")
    group.addoption("--attack-model", default="claude", choices=["claude", "obedient"],
                    help="claude: the real API. obedient: the obedient model on the fake API of labkit.")
    group.addoption("--attack-results", default=None, help="Write the pass rates to this JSON file.")
    group.addoption("--attack-label", default="run", help="The name of the run in the result file.")


@pytest.fixture(scope="session")
def attack_model(request: pytest.FixtureRequest) -> str:
    model = request.config.getoption("--attack-model")
    plugin_on = request.config.pluginmanager.has_plugin("labkit.plugin")
    if model == "obedient" and not plugin_on:
        pytest.exit("MODEL=obedient needs the fake API of labkit: do not pass -p no:labkit.plugin.", 2)
    if model == "claude" and plugin_on:
        pytest.exit("The real model needs `-p no:labkit.plugin`. Use `make attacks`.", 2)
    if model == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.exit("ANTHROPIC_API_KEY is not set. Put your key in .env, or use MODEL=obedient.", 2)
    return model


@pytest.fixture(scope="session")
def poisoned() -> None:
    """Fail with a clear message when the poisoned material is not in the database."""
    import psycopg

    url = os.environ.get("DATABASE_URL", "postgresql://assistant:assistant@localhost:5432/assistant")
    with psycopg.connect(url, connect_timeout=3) as connection:
        count = connection.execute("SELECT count(*) FROM documents WHERE id LIKE 'poisoned-%'").fetchone()[0]
    if not count:
        pytest.exit("No poisoned document is in the database. Write data/poisoned/ and run `make poison`.", 2)


@pytest.fixture(scope="session")
def mcp_servers() -> Iterator[dict[str, Any]]:
    from labkit.processes import start_servers

    servers = start_servers(Path(tempfile.mkdtemp(prefix="lab-attacks-")))
    for server in servers.values():
        if server.error:
            pytest.exit(server.error, 2)
    yield servers
    for server in servers.values():
        server.stop()


@pytest.fixture
def attack_client(attack_model, poisoned, mcp_servers, monkeypatch, request) -> Any:
    """Your API in this process, with the graph, and the model of the run."""
    from starlette.testclient import TestClient

    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("AGENT_PLANNER", "off")
    if attack_model == "obedient":
        from labkit import obedient
        from labkit.plugin import guardrails_url

        request.getfixturevalue("fake").always(obedient.claude_reply)
        # The plugin turns the guardrails server off for the checks. The suite uses it when it
        # runs (week 20), and else runs without it.
        monkeypatch.setenv("GUARDRAILS_URL", guardrails_url() if _answers(guardrails_url()) else "")
    else:
        # A replay from the response cache is an old answer. The suite measures new answers.
        monkeypatch.setenv("RESPONSE_CACHE", "off")
    from assistant.api import app

    return TestClient(app)


def _answers(url: str) -> bool:
    import httpx

    try:
        return httpx.get(f"{url.rstrip('/')}/v1/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    properties = dict(report.user_properties)
    if report.when == "call" and "case" in properties:
        case = properties["case"]
        _rows.append({"id": case["id"], "kind": case["kind"], "passed": report.passed,
                      "reasons": properties.get("reasons", [])})


def pytest_sessionfinish(session: pytest.Session) -> None:
    path = session.config.getoption("--attack-results")
    if path and _rows:
        model = session.config.getoption("--attack-model")
        result = write_results(Path(path), session.config.getoption("--attack-label"), model, _rows)
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            from evals.attacks import table

            reporter.write_line("")
            reporter.write_line(table(result))
            reporter.write_line(f"Wrote {path}")
        # A run with a result file is a measurement: a successful attack is a result, not an
        # error of the run. `make attack-report` is the gate. Errors of the run still fail.
        if session.exitstatus == pytest.ExitCode.TESTS_FAILED:
            session.exitstatus = pytest.ExitCode.OK
