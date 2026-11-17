"""Week 22 live check: the open model on your pod, through your gateway.

Run it with `make check-live WEEK=22` while vLLM runs on the pod. It sends one short question to
the route qwen3-8b. The request itself costs nothing more than the time of the pod, which you pay
by the hour. It needs GATEWAY_URL and GATEWAY_KEY in your `.env` file, and VLLM_API_BASE and
VLLM_API_KEY for the gateway.
"""

from __future__ import annotations

import os

import pytest

from phase6_helpers import OPEN


def test_the_open_model_on_the_pod_answers_through_your_gateway(live):
    import anthropic

    if not os.environ.get("GATEWAY_URL"):
        pytest.fail("GATEWAY_URL is not set. Put it in the file .env (Phase 6, week 21).", pytrace=False)
    client = anthropic.Anthropic(base_url=os.environ["GATEWAY_URL"], api_key=os.environ.get("GATEWAY_KEY", ""))
    message = client.messages.create(
        model=OPEN, max_tokens=2048, messages=[{"role": "user", "content": "Name one public dataset about water."}]
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    # Qwen3 thinks by default, so the limit leaves room for the thinking and the answer.
    assert text.strip(), f"The open model gave no text (did the thinking use all the tokens?): {message}"
    print(f"\n  {OPEN}: {text[:200]!r} ({message.usage.output_tokens} output tokens)")
