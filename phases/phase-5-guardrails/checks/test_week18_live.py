"""Week 18 live check: one attack case of each kind on the real Claude API.

Run it with `make check-live WEEK=18`. It calls the real Claude API, so it costs money: about
$0.01 for the four cases (estimate: about 20 requests of about 5,000 input tokens at the
prices of Claude Haiku 5.5). It needs ANTHROPIC_API_KEY in your `.env` file, Postgres with the
documents and the poisoned material (`make poison`), both model services, and from week 19
Keycloak (`make up`), because the live run uses the real sign-in.

The check runs the suite as `make attacks` does (`-p no:labkit.plugin`), for the first case of
each kind. It does not ask for a pass: a real model can obey an attack. It checks that the suite
runs on the real model and writes a result for each kind.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CASES = REPO / "evals" / "attacks.jsonl"
KINDS = ("direct", "poisoned_document", "tool_result", "exfiltration")


def test_one_case_of_each_kind_runs_on_the_real_model(live, tmp_path):
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    chosen = [next(case for case in cases if case["kind"] == kind) for kind in KINDS]
    out = tmp_path / "attacks-live.json"
    command = [sys.executable, "-m", "pytest", "tests/attacks", "-q", "-p", "no:labkit.plugin", "-p", "no:cacheprovider",
               "--attack-model", "claude", "--attack-label", "live", "--attack-results", str(out),
               "-k", " or ".join(f"{case['id']}-{case['kind']}" for case in chosen)]
    process = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=1800)
    assert process.returncode == 0, f"The suite did not run on the real model:\n{process.stdout[-3000:]}{process.stderr[-2000:]}"
    assert out.exists(), f"The suite wrote no result file:\n{process.stdout[-3000:]}"
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["model"] == "claude" and sorted(result["kinds"]) == sorted(KINDS), result
    assert {row["id"] for row in result["rows"]} == {case["id"] for case in chosen}, result["rows"]
    for row in result["rows"]:
        print(f"\n  {row['id']}  {row['kind']:<18} {'passed' if row['passed'] else 'failed'}  {'; '.join(row['reasons'])}")
