"""Week 21 live check: your gateway (`make up`) with the real Claude API.

Run it with `make check-live WEEK=21`. It sends one short question to Claude through your
gateway and reads the budget of the user, so it costs money: less than $0.01 (estimate: one
request of about 50 input and 100 output tokens at the prices of Claude Haiku 5.5). It needs GATEWAY_URL, GATEWAY_KEY and
LITELLM_MASTER_KEY in your `.env` file, and the gateway with the keys of the providers.

The check does not remove your Claude key: the offline check of week 21 tests the fallback.
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

from phase6_helpers import CLAUDE, gateway_config


def admin(path: str, method: str = "GET", body: dict | None = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {os.environ.get('LITELLM_MASTER_KEY', '')}"}
    return httpx.request(method, f"{os.environ['GATEWAY_URL']}{path}", headers=headers, json=body, timeout=30)


@pytest.fixture
def gateway_settings(live) -> None:
    for name in ("GATEWAY_URL", "GATEWAY_KEY", "LITELLM_MASTER_KEY"):
        if not os.environ.get(name):
            pytest.fail(f"{name} is not set. Put it in the file .env (Phase 6, week 21).", pytrace=False)


def test_claude_answers_through_your_gateway_and_the_spend_of_the_user_is_counted(gateway_settings):
    import anthropic

    client = anthropic.Anthropic(base_url=os.environ["GATEWAY_URL"], api_key=os.environ["GATEWAY_KEY"])
    user = f"live-check-{uuid.uuid4().hex[:8]}"
    message = client.messages.create(
        model=CLAUDE, max_tokens=100, messages=[{"role": "user", "content": "Name one public dataset about water."}],
        extra_headers={"x-litellm-end-user-id": user},
    )
    assert message.content and message.content[0].text, f"No text in the answer: {message}"
    deadline, spend = time.monotonic() + 60, 0.0
    while time.monotonic() < deadline and not spend:
        response = admin(f"/customer/info?end_user_id={user}")
        spend = float(response.json().get("spend") or 0) if response.status_code == 200 else 0.0
        time.sleep(2)
    assert spend > 0, "Your gateway counted no spend for the user. Give the Claude route its prices."
    print(f"\n  {CLAUDE} answered through the gateway; spend of {user}: ${spend:.6f}")


def test_your_gateway_has_the_budget_for_each_user(gateway_settings):
    name = (gateway_config().get("litellm_settings") or {}).get("max_end_user_budget_id")
    assert name, "gateway/config.yaml has no litellm_settings.max_end_user_budget_id."
    response = admin("/budget/info", "POST", {"budgets": [name]})
    assert response.status_code == 200 and response.json(), (
        f"Your gateway has no budget `{name}`. Create it with POST /budget/new (week 21, step 3): {response.text[:500]}"
    )
    print(f"\n  budget {name}: {response.json()}")
