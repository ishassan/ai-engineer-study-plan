"""The attack suite: one test for each case of evals/attacks.jsonl. Phase 5, week 18.

This file is complete. A test fails when the attack of its case succeeded. The suite as a
whole is a measurement, not a gate: the result file holds the pass rate for each kind.
"""

from __future__ import annotations

import pytest

from evals.attacks import load_cases, run_attack, verdict

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[f"{case['id']}-{case['kind']}" for case in CASES])
def test_the_attack_does_not_succeed(case, attack_client, request):
    run = run_attack(attack_client, case)
    reasons = verdict(case, run)
    request.node.user_properties.append(("case", case))
    request.node.user_properties.append(("reasons", reasons))
    assert not reasons, f"{case['id']} ({case['kind']}): " + "; ".join(reasons) + f". Events: {run['events']}"
