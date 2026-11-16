"""Week 14 live check: the graph answers one question on Claude and on OpenAI.

Run it with `make check-live WEEK=14`. It calls the real Claude API and the real OpenAI
API, so it costs money: about $0.01 for both runs (estimate). It needs ANTHROPIC_API_KEY
and OPENAI_API_KEY in your `.env` file, and Postgres and both model services (`make up`).
"""

from __future__ import annotations

import os

import pytest

from labkit.sse import ask

QUESTION = "Which datasets are about crude oil production?"


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_the_graph_answers_on_each_provider(provider, live, client, database, monkeypatch):
    if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        pytest.fail("OPENAI_API_KEY is not set. Put your OpenAI key in the file .env.", pytrace=False)
    monkeypatch.setenv("AGENT_IMPL", "langgraph")
    monkeypatch.setenv("PROVIDER", provider)
    result = ask(client, QUESTION)

    assert result.errors == [], result.errors
    assert result.answer is not None and result.answer["dataset_ids"], "The answer names at least one dataset."
    assert "search_datasets" in [tool["name"] for tool in result.tools]
    done = result.done
    assert done["cost_usd"] > 0 and done["requests"] >= 2
    print(f"\n  {provider:9} {done['model']}  {done['requests']} requests  ${done['cost_usd']:.5f}")
