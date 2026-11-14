"""Week 3 live check, which is the exit test of Phase 1.

Run it with `make check-live WEEK=3`. It runs your 30 questions against the
real API with the response cache off: about 90 requests, which cost about $0.05.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_30_questions_run_from_one_command_with_the_cache_off(live, tmp_path, database, capsys):
    out = tmp_path / "all.jsonl"
    process = subprocess.run(
        [sys.executable, "-m", "evals.run", "--set", "all", "--no-cache", "--out", str(out)],
        cwd=REPO,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    assert process.returncode == 0, process.stderr[-3000:]

    results = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert len(results) == 30
    for result in results:
        assert result["input_tokens"] > 0 and result["output_tokens"] > 0, result
        assert result["cost_usd"] > 0, f"{result['id']}: with the cache off, each question costs money."
        assert result["latency_ms"] > 0

    log = [json.loads(line) for line in live.read_text().splitlines() if line.strip()]
    assert len(log) >= 30, "Each request to Claude must be in the request log."
    assert not any(line["replayed"] for line in log), "The response cache must be off for this run."
    cache_reads = [line for line in log if line["cache_read_input_tokens"] > 0]
    assert cache_reads, (
        "No request read the prompt cache. Check that the tools and the system prompt together "
        "have at least 512 tokens, and that the cache breakpoint is on the system prompt."
    )

    passed = sum(result["passed"] for result in results)
    cost = sum(result["cost_usd"] for result in results)
    latencies = sorted(result["latency_ms"] for result in results)
    read = sum(line["cache_read_input_tokens"] for line in log)
    fresh = sum(line["input_tokens"] + line["cache_creation_input_tokens"] for line in log)
    with capsys.disabled():
        print(f"\n  passed            {passed} of 30")
        print(f"  requests          {len(log)}")
        print(f"  total cost        ${cost:.4f}")
        print(f"  median latency    {latencies[len(latencies) // 2] / 1000:.1f} s for one question")
        print(f"  cache reads       {len(cache_reads)} of {len(log)} requests")
        print(f"  input from cache  {read / max(1, read + fresh):.0%} of the input tokens")
        print("  Write these numbers in phases/phase-1-claude-api/RESULTS.md.")
