"""Week 28 check: the exit test of the plan.

Run it with `make check WEEK=28`, or see the full table with `make exit-test`. The check runs
scripts/exit_test.py, which reads the files that prove each of the 12 items of the plan's exit
test. It needs no service. Each item must be `ok`. The parts that only you can confirm (real users,
the public repository, your CV) are questions: the check prints them and does not answer them.
"""

from __future__ import annotations

import json
import subprocess
import sys

from labkit.capstone import REPO


def test_each_item_of_the_exit_test_has_its_evidence():
    result = subprocess.run(
        [sys.executable, "scripts/exit_test.py", "--json"], cwd=REPO, capture_output=True, text=True, timeout=120
    )
    assert result.stdout.strip(), f"scripts/exit_test.py printed nothing.\n{result.stderr[-2000:]}"
    items = json.loads(result.stdout)
    open_items = [item for item in items if item["state"] != "ok"]
    lines = [
        f"{item['item']}. [{item['state']}] {item['text']}\n   - " + "\n   - ".join(item["problems"])
        for item in open_items
    ]
    assert not open_items, "Items of the exit test without their evidence (make exit-test):\n" + "\n".join(lines)
    print("\nOnly you can confirm these:")
    for item in items:
        for question in item["questions"]:
            print(f"{item['item']:>2}. {question}")
