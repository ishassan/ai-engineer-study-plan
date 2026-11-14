"""Pytest plugin for the lab checks.

Offline checks (the default): the plugin starts the fake Claude API before any
test runs and points the `anthropic` SDK at it with ANTHROPIC_BASE_URL. The
response cache and the request log go to a temporary folder, so a check never
touches your own cache or logs.

Live checks (`--live`): the plugin changes nothing. The checks in files named
`*_live.py` call the real API with the key from your `.env` file.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator

import pytest

from labkit.fake_claude import FakeClaude, FakeClaudeServer

REPO = Path(__file__).resolve().parent.parent
_state: dict[str, Any] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run the live checks, which call the real Claude API and cost money.",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--live"):
        return
    server = FakeClaudeServer()
    fake = server.start()
    work = Path(tempfile.mkdtemp(prefix="lab-checks-"))
    _state.update(server=server, fake=fake, work=work)
    os.environ.update(
        ANTHROPIC_BASE_URL=fake.url,
        ANTHROPIC_API_KEY="offline-check-key",
        RESPONSE_CACHE="on",
        RESPONSE_CACHE_DIR=str(work / "responses"),
        REQUEST_LOG_PATH=str(work / "requests.jsonl"),
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    server = _state.pop("server", None)
    if server is not None:
        server.stop()
        shutil.rmtree(_state.pop("work"), ignore_errors=True)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    live_run = config.getoption("--live")
    for item in items:
        is_live = item.path.name.endswith("_live.py")
        if is_live and not live_run:
            item.add_marker(pytest.mark.skip(reason="live check: run it with `make check-live`"))
        if not is_live and live_run:
            item.add_marker(pytest.mark.skip(reason="offline check: run it with `make check`"))


@pytest.fixture(autouse=True)
def _clean_state(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Each offline check starts with an empty cache, an empty log and an empty script."""
    if "fake" in _state:
        _state["fake"].reset()
        shutil.rmtree(_state["work"] / "responses", ignore_errors=True)
        (_state["work"] / "requests.jsonl").unlink(missing_ok=True)
        monkeypatch.setenv("RESPONSE_CACHE", "on")
    yield


@pytest.fixture
def fake() -> FakeClaude:
    """The fake Claude API. Script its replies and read the requests it received."""
    if "fake" not in _state:
        pytest.skip("The fake Claude API does not run in a live check.")
    return _state["fake"]


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Prepare a live check: a real API key, and a cache and a log in a temporary folder.

    The live check then makes real requests also when your own cache holds the
    same question. The fixture returns the path of the temporary request log.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.fail("ANTHROPIC_API_KEY is not set. Put your key in the file .env.", pytrace=False)
    log_path = tmp_path / "requests.jsonl"
    monkeypatch.setenv("RESPONSE_CACHE", "on")
    monkeypatch.setenv("RESPONSE_CACHE_DIR", str(tmp_path / "responses"))
    monkeypatch.setenv("REQUEST_LOG_PATH", str(log_path))
    return log_path


@pytest.fixture
def client() -> Any:
    """An HTTP client for your FastAPI app, in this process."""
    from starlette.testclient import TestClient

    try:
        from assistant.api import app
    except ModuleNotFoundError as error:
        if error.name not in {"assistant", "assistant.api"}:
            raise  # Your own code has a broken import: show it.
        pytest.fail(
            "The package `assistant` does not exist. Run `make start PHASE=1` first.",
            pytrace=False,
        )
    return TestClient(app)


@pytest.fixture
def request_log() -> Any:
    """A function that returns the lines of the request log as a list of dicts."""

    def read() -> list[dict[str, Any]]:
        path = Path(os.environ["REQUEST_LOG_PATH"])
        assert path.exists(), (
            f"No request log at {path}. Write one JSON line for each Claude request to the "
            "path that get_settings().request_log_path gives."
        )
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    return read


@pytest.fixture
def cache_files() -> Any:
    """A function that returns the files in the response cache folder."""

    def read() -> list[Path]:
        folder = Path(os.environ["RESPONSE_CACHE_DIR"])
        return sorted(path for path in folder.rglob("*") if path.is_file()) if folder.exists() else []

    return read


@pytest.fixture(scope="session")
def catalogue() -> list[dict[str, Any]]:
    """The 50 datasets of data/catalogue.json."""
    return json.loads((REPO / "data" / "catalogue.json").read_text())


@pytest.fixture(scope="session")
def database() -> None:
    """Fail with a clear message when Postgres does not run or has no data."""
    import psycopg

    url = os.environ.get("DATABASE_URL", "postgresql://assistant:assistant@localhost:5432/assistant")
    try:
        with psycopg.connect(url, connect_timeout=3) as connection:
            count = connection.execute("SELECT count(*) FROM datasets").fetchone()[0]
    except psycopg.Error as error:
        pytest.fail(f"Postgres is not ready. Run `make up` first.\n{error}", pytrace=False)
    assert count >= 50, "The table datasets is not loaded. Run `make up`."


@pytest.fixture
def questions() -> list[dict[str, Any]]:
    """The test questions that you wrote in evals/questions.jsonl."""
    path = REPO / "evals" / "questions.jsonl"
    assert path.exists(), "evals/questions.jsonl does not exist. Run `make start PHASE=1` first."
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
