"""Pytest plugin for the lab checks.

Offline checks (the default): the plugin starts the fake Claude API before any
test runs and points the `anthropic` SDK at it with ANTHROPIC_BASE_URL. From Phase 4
it also starts the fake OpenAI API and points the `openai` SDK at it with
OPENAI_BASE_URL. The response cache and the request log go to a temporary folder, so
a check never touches your own cache or logs.

From Phase 5 it also starts a fake authorization server (labkit/auth.py) and points the
AUTH_* settings at it, when the packages of the sign-in (PyJWT and cryptography) are
installed. The `client` fixture then sends a token with each request.

From Phase 6 the checks run without your model gateway: the plugin clears GATEWAY_URL and
GATEWAY_KEY. The fixture `gateway` starts a gateway with your configuration and the fake APIs as
its providers (labkit/gateway.py) and points these settings at it. `pytest --gateway` does the
same for all offline checks of the run, so you can see that the checks of Phases 1 to 5 still
pass when each model call goes through your gateway.

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
from labkit.fake_openai import FakeOpenAI, FakeOpenAIServer

REPO = Path(__file__).resolve().parent.parent
_state: dict[str, Any] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run the live checks, which call the real Claude API and cost money.",
    )
    parser.addoption(
        "--gateway",
        action="store_true",
        default=False,
        help="Phase 6: send the model calls of all offline checks through a gateway with your "
        "gateway/config.yaml and the fake APIs as providers.",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--live"):
        return
    server = FakeClaudeServer()
    fake = server.start()
    openai_server = FakeOpenAIServer()
    fake_openai = openai_server.start()
    work = Path(tempfile.mkdtemp(prefix="lab-checks-"))
    _state.update(server=server, fake=fake, openai_server=openai_server, fake_openai=fake_openai, work=work)
    _start_fake_auth(work)
    # Phase 5, week 20: the checks of the earlier weeks run without the guardrails server, so a
    # GUARDRAILS_URL in your .env does not change them. The checks of week 20 and the attack
    # suite turn it on again with guardrails_url().
    _state["guardrails_url"] = os.environ.get("GUARDRAILS_URL", "")
    os.environ["GUARDRAILS_URL"] = ""
    # Phase 6: the checks call the fake APIs directly. The fixture `gateway` (and the option
    # --gateway) put a gateway with your configuration in between.
    os.environ["GATEWAY_URL"] = ""
    os.environ["GATEWAY_KEY"] = ""
    if config.getoption("--gateway"):
        gateway = _check_gateway()
        if gateway.error:
            raise pytest.UsageError(f"--gateway: {gateway.error}")
        os.environ.update(GATEWAY_URL=gateway.url, GATEWAY_KEY=gateway_key())
    os.environ.update(
        ANTHROPIC_BASE_URL=fake.url,
        ANTHROPIC_API_KEY="offline-check-key",
        OPENAI_BASE_URL=fake_openai.url,
        OPENAI_API_KEY="offline-check-key",
        RESPONSE_CACHE="on",
        RESPONSE_CACHE_DIR=str(work / "responses"),
        REQUEST_LOG_PATH=str(work / "requests.jsonl"),
    )


def _start_fake_auth(work: Path) -> None:
    try:
        from labkit import auth
    except ImportError:  # Phases 1 to 3 do not install PyJWT: no sign-in before Phase 5.
        return
    auth_server = auth.FakeAuthServer(work)
    auth.FAKE = auth_server.start()
    _state["auth_server"] = auth_server
    issuer = auth.FAKE.issuer
    os.environ.update(
        AUTH_ISSUER=issuer,
        AUTH_METADATA_URL=f"{issuer}/.well-known/openid-configuration",
        AUTH_TOKEN_URL=f"{issuer}/protocol/openid-connect/token",
        AUTH_CLIENT_ID=auth.SERVICE_CLIENT_ID,
        AUTH_CLIENT_SECRET=auth.SERVICE_CLIENT_SECRET,
    )


def _check_gateway() -> Any:
    """The gateway of this run of the checks. It starts at the first call."""
    if "gateway" not in _state:
        from labkit.gateway import CheckGateway

        gateway = CheckGateway(_state["fake"], _state["fake_openai"])
        _state["gateway"] = gateway
        gateway.start()
    return _state["gateway"]


def gateway_key() -> str:
    from labkit.gateway import MASTER_KEY

    return MASTER_KEY


def pytest_unconfigure(config: pytest.Config) -> None:
    gateway = _state.pop("gateway", None)
    if gateway is not None:
        gateway.stop()
    auth_server = _state.pop("auth_server", None)
    if auth_server is not None:
        auth_server.stop()
    server = _state.pop("server", None)
    if server is not None:
        server.stop()
        _state.pop("openai_server").stop()
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
        _state["fake_openai"].reset()
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
def fake_openai() -> FakeOpenAI:
    """The fake OpenAI API. Script its replies and read the requests it received."""
    if "fake_openai" not in _state:
        pytest.skip("The fake OpenAI API does not run in a live check.")
    return _state["fake_openai"]


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Phase 6: a gateway with your gateway/config.yaml, and the fake APIs as its providers.

    The fixture points GATEWAY_URL and GATEWAY_KEY at it and turns the response cache off, so
    each model call of the test goes through the gateway.
    """
    if "fake" not in _state:
        pytest.skip("The check gateway does not run in a live check.")
    check_gateway = _check_gateway()
    if check_gateway.error:
        pytest.fail(check_gateway.error, pytrace=False)
    monkeypatch.setenv("GATEWAY_URL", check_gateway.url)
    monkeypatch.setenv("GATEWAY_KEY", gateway_key())
    monkeypatch.setenv("RESPONSE_CACHE", "off")
    return check_gateway


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
    """An HTTP client for your FastAPI app, in this process.

    While the fake authorization server runs, each request without an Authorization header
    gets a token for the user of its X-User header (or `anonymous`).
    """
    try:
        from assistant.api import app
    except ModuleNotFoundError as error:
        if error.name not in {"assistant", "assistant.api"}:
            raise  # Your own code has a broken import: show it.
        pytest.fail(
            "The package `assistant` does not exist. Run `make start PHASE=1` first.",
            pytrace=False,
        )
    return make_client(app)


def guardrails_url() -> str:
    """The address of the guardrails server: GUARDRAILS_URL of your .env, or the default of Compose."""
    return _state.get("guardrails_url") or "http://localhost:8100"


def make_client(app: Any) -> Any:
    """A TestClient for the app. While the fake authorization server runs, it signs in each request."""
    from starlette.testclient import TestClient

    try:
        from labkit.auth import SignedIn
    except ImportError:  # PyJWT is not installed: no sign-in before Phase 5.
        return TestClient(app)

    class SignedInTestClient(SignedIn, TestClient):
        pass

    return SignedInTestClient(app)


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
