"""Week 1 live check: one real request to Claude Haiku 5.5, and one replay.

Run it with `make check-live WEEK=1`. It makes one real request, which costs
less than $0.001.
"""

from __future__ import annotations

from labkit.sse import ask

QUESTION = "In one sentence: what is a data catalogue?"


def test_a_real_request_streams_and_the_second_one_is_replayed(client, live, capsys):
    first = ask(client, QUESTION)

    assert first.status_code == 200
    assert first.errors == [], first.errors
    assert first.text.strip(), "The real API gave no text."
    done = first.done
    assert done["input_tokens"] > 0 and done["output_tokens"] > 0
    assert 0 < done["cost_usd"] < 0.01, f"One short request must cost far below 1 cent: {done}"
    assert done["latency_ms"] > 0

    second = ask(client, QUESTION)
    assert second.text == first.text, "The replay must give the saved answer."
    assert second.done["cost_usd"] == 0, "The second request must come from the response cache."

    with capsys.disabled():
        print(f"\n  answer   {first.text.strip()[:200]}")
        print(
            f"  tokens   {done['input_tokens']} in, {done['output_tokens']} out"
            f"   cost ${done['cost_usd']:.6f}   latency {done['latency_ms']:.0f} ms"
        )
        print(f"  replay   cost ${second.done['cost_usd']:.6f}   latency {second.done['latency_ms']:.0f} ms")
