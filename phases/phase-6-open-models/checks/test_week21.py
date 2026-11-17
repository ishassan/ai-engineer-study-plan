"""Week 21: the model gateway.

Each check sends requests through a LiteLLM gateway with your gateway/config.yaml. The
providers of that gateway are the fake Claude API and the fake OpenAI API. Each provider gets a
key that only the gateway has, so a check sees whether a request came through the gateway.

Fixed names: the routes `claude-haiku-5-5` and `gpt-6-luna` (the default CLAUDE_MODEL and
OPENAI_MODEL), the settings GATEWAY_URL and GATEWAY_KEY (given/assistant/config.py), and
`litellm_settings.max_end_user_budget_id` in gateway/config.yaml.
"""

from __future__ import annotations

import math
import time
from typing import Any

import pytest

from labkit import fake_claude
from labkit.gateway import CHECK_BUDGET_USD, UPSTREAM_KEYS
from phase6_helpers import (
    CLAUDE,
    OPENAI,
    answers_for,
    ask,
    claude_answer,
    dataset_cases,
    errors_of,
    events_text,
    gateway_config,
    new_user,
    openai_answer,
    openai_keys,
    through_gateway_claude,
)

QUESTION = "Which datasets show the electricity consumption by sector?"
REFUSED = fake_claude.error_reply(401, "authentication_error", "invalid x-api-key")
# The check gateway gives the default budget of your configuration CHECK_BUDGET_USD. One answer
# of this size costs much more at the prices of Claude Haiku 5.5, and the fake API reports it.
BUDGET_USD = CHECK_BUDGET_USD
BIG_USAGE = {"input_tokens": 1000, "output_tokens": 10_000_000_000}
COOLDOWN_SECONDS = 6


# ---- step 2: the gateway and the routes -----------------------------------------------------------


def test_the_gateway_starts_with_your_configuration(gateway):
    status, body = gateway.admin("GET", "/health/readiness")
    assert status == 200, f"The gateway is not ready: {status} {body}"


def model_info(gateway) -> dict[str, dict]:
    status, body = gateway.admin("GET", "/model/info")
    assert status == 200, f"GET /model/info of the gateway answered {status}: {body}"
    return {row.get("model_name"): row for row in body.get("data", [])}


PRICE_NAMES = {"input_cost_per_token": "input", "output_cost_per_token": "output"}


def configured_prices(route: str) -> dict[str, Any]:
    """The prices that gateway/config.yaml gives the route (litellm_params or model_info)."""
    entries = [entry for entry in gateway_config().get("model_list") or [] if entry.get("model_name") == route]
    assert entries, f"gateway/config.yaml has no route `{route}` in model_list (step 2)."
    prices: dict[str, Any] = {}
    for entry in entries:
        for part in ("model_info", "litellm_params"):
            for name in PRICE_NAMES:
                value = (entry.get(part) or {}).get(name)
                if value is not None:
                    prices.setdefault(name, value)
    return prices


@pytest.mark.parametrize("route", [CLAUDE, OPENAI])
def test_the_gateway_has_a_route_with_a_price_for_each_model(gateway, route):
    from assistant.config import PRICES_PER_MTOK

    routes = model_info(gateway)
    assert route in routes, (
        f"The gateway has no route `{route}` (it has {sorted(routes)}). Add it to model_list in "
        "gateway/config.yaml (step 2)."
    )
    # The price list that comes with LiteLLM can know the model too, but it changes with each
    # release. The route must state the prices of assistant/config.py, so that the spend that
    # the gateway counts for a user is the cost that the assistant writes in its results.
    prices = configured_prices(route)
    for name, kind in PRICE_NAMES.items():
        expected = PRICES_PER_MTOK[route][kind] / 1_000_000
        value = prices.get(name)
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"The route `{route}` in gateway/config.yaml has no {name}. Set input_cost_per_token and "
            "output_cost_per_token, so the gateway can count the spend of each user (step 3)."
        )
        assert math.isclose(value, expected, rel_tol=1e-6), (
            f"The route `{route}` has {name} {value}, but PRICES_PER_MTOK in assistant/config.py gives "
            f"{expected:.10f} US dollars for one token ({kind} price for one million tokens / 1,000,000)."
        )


def test_the_handwritten_loop_calls_claude_through_the_gateway(client, fake, gateway):
    fake.always(claude_answer("Two datasets show it."))
    result = ask(client, QUESTION)
    assert result.answer is not None, f"No answer through the gateway. Events: {events_text(result)}"
    assert through_gateway_claude(fake), (
        "The fake Claude API got the request from your code, not from the gateway. With GATEWAY_URL "
        "set, send each model call to GATEWAY_URL with the key GATEWAY_KEY (step 2)."
    )
    body = fake.requests[0]
    assert fake_claude.has_cache_control(body), "The request lost its cache breakpoint on the way through the gateway."
    assert body.get("output_config"), "The request lost output_config (the typed answer) on the way through the gateway."
    assert body.get("tools"), "The request lost its tools on the way through the gateway."


def test_the_graph_calls_claude_through_the_gateway(client, fake, gateway, graph, monkeypatch):
    monkeypatch.setenv("PROVIDER", "anthropic")
    fake.always(claude_answer("Two datasets show it."))
    result = ask(client, QUESTION)
    assert result.answer is not None, f"No answer through the gateway. Events: {events_text(result)}"
    assert through_gateway_claude(fake), (
        "The graph called the fake Claude API directly. With GATEWAY_URL set, give ChatAnthropic the "
        "address and the key of the gateway (step 2)."
    )
    assert fake_claude.has_cache_control(fake.requests[0]), "The graph request lost its cache breakpoint."


def test_the_graph_calls_openai_through_the_gateway(client, fake_openai, gateway, graph, monkeypatch):
    monkeypatch.setenv("PROVIDER", "openai")
    fake_openai.always(openai_answer("Two datasets show it."))
    result = ask(client, QUESTION)
    assert result.answer is not None, f"No answer through the gateway. Events: {events_text(result)}"
    assert openai_keys(fake_openai) == {UPSTREAM_KEYS["openai"]}, (
        "The graph called the fake OpenAI API directly. With GATEWAY_URL set, give ChatOpenAI the "
        "address of the gateway (GATEWAY_URL + /v1) and the key GATEWAY_KEY (step 2)."
    )


# ---- step 3: the budget of each user ------------------------------------------------------------


def budget_id() -> str:
    """The default budget of each user in your configuration. The check gateway created it."""
    value = (gateway_config().get("litellm_settings") or {}).get("max_end_user_budget_id")
    assert value, (
        "gateway/config.yaml has no litellm_settings.max_end_user_budget_id: the budget that each user "
        "gets (step 3)."
    )
    return value


def wait_for_spend(gateway, user: str, seconds: float = 60) -> float:
    """The gateway writes the spend every few seconds. Wait until the spend of the user is over the budget."""
    deadline, spend = time.monotonic() + seconds, 0.0
    while time.monotonic() < deadline:
        status, body = gateway.admin("GET", f"/customer/info?end_user_id={user}")
        if status == 200 and isinstance(body, dict):
            spend = float(body.get("spend") or 0)
            if spend > BUDGET_USD:
                return spend
        time.sleep(1)
    return spend


@pytest.mark.parametrize("impl", ["handwritten", "langgraph"])
def test_the_budget_of_a_user_stops_only_that_user(client, fake, fake_openai, gateway, mcp_servers, monkeypatch, impl):
    monkeypatch.setenv("AGENT_IMPL", impl)
    monkeypatch.setenv("AGENT_PLANNER", "off")
    monkeypatch.setenv("PROVIDER", "anthropic")
    budget_id()
    spender, other = new_user(), new_user()
    fake.always(claude_answer("An expensive answer.", usage=BIG_USAGE))
    fake_openai.always(openai_answer("An expensive answer.", usage=BIG_USAGE))
    first = ask(client, QUESTION, spender)
    assert first.answer is not None, f"The first question of the user got no answer. Events: {events_text(first)}"
    spend = wait_for_spend(gateway, spender)
    assert spend > BUDGET_USD, (
        f"The gateway counted no spend for the user `{spender}` (spend {spend}). Send the user with each "
        "model call (for example the header x-litellm-end-user-id), and give each route its prices (step 3)."
    )
    seen = len(fake.requests) + len(fake_openai.requests)
    second = ask(client, "And which of them is updated each month?", spender)
    assert len(fake.requests) + len(fake_openai.requests) == seen, (
        f"The user is over the budget, but the gateway still sent a request to a model. Set "
        f"max_end_user_budget_id (step 3). Events: {events_text(second)}"
    )
    assert second.answer is None and any("budget" in message.lower() for message in errors_of(second)), (
        f"Over the budget, the user must get an error that names the budget, not an answer. Events: "
        f"{events_text(second)}"
    )
    fake.always(claude_answer("A cheap answer."))
    third = ask(client, QUESTION, other)
    assert third.answer is not None, (
        f"Another user was refused too: the budget must be for each user, not for all. Events: {events_text(third)}"
    )


# ---- steps 3 and 4: without the Claude key ------------------------------------------------------
# After the refusals of Claude, the gateway keeps the Claude route out of use for a few seconds
# (its cooldown, 5 s by default). These checks come last and wait that long when they end.


@pytest.fixture
def claude_refuses(fake):
    fake.always(REFUSED)
    yield
    time.sleep(COOLDOWN_SECONDS)


def test_without_the_claude_key_the_requests_fall_back_to_openai(client, fake, fake_openai, gateway, claude_refuses):
    fake_openai.always(openai_answer("OpenAI answered."))
    result = ask(client, QUESTION)
    assert fake.requests, "The gateway did not try Claude first."
    assert fake_openai.requests, (
        f"Claude refused the key (401) and the gateway did not try OpenAI. Add a fallback from "
        f"`{CLAUDE}` to `{OPENAI}` in router_settings (step 3). Events: {events_text(result)}"
    )
    assert {body.get("model") for body in fake_openai.requests} == {OPENAI}, (
        f"The fallback must call the OpenAI model `{OPENAI}`: {[b.get('model') for b in fake_openai.requests]}"
    )
    assert result.answer is not None and "OpenAI answered" in result.answer.get("answer", ""), (
        f"The answer of the fallback did not reach the user. Events: {events_text(result)}"
    )




def test_the_test_set_passes_through_the_gateway_without_the_claude_key(fake, fake_openai, gateway, claude_refuses):
    from evals.run_testset import run_case

    cases = dataset_cases(5)
    assert len(cases) == 5, "evals/testset.jsonl needs at least 5 cases that expect datasets and no passage."
    fake_openai.always(answers_for(cases))
    rows = [run_case(case, run_name="check-week21") for case in cases]
    failed = [(row["id"], row["errors"]) for row in rows if not row["code_pass"]]
    assert not failed, f"Without the Claude key these cases did not pass through the gateway: {failed}"
    assert fake_openai.requests, "The cases did not reach OpenAI through the fallback."
