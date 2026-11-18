"""The exit test of the plan: each item of the capstone list, with the evidence for it. Phase 7.

    make exit-test                 read the files that prove each item
    make exit-test ARGS=--run      also run the offline checks of the weeks that built each item
    make exit-test ARGS=--json     the result as JSON (the check of week 28 reads it)

For each item the script prints its evidence and a state:

    ok        the files exist and meet the rule of the item (and its checks pass, with --run)
    missing   a file that proves the item does not exist
    fail      the files exist, but a rule of the item is not met (or a check fails, with --run)

Some parts of an item only a person can confirm, for example real users, a public repository and
the CV. The script prints them as questions after the table. The exit code is 1 when an item is
not ok.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # for the package labkit

from labkit.capstone import ITEMS  # noqa: E402

MAX_PROBLEMS = 6  # the problems that the table prints for each item


def run_week(week: int) -> bool:
    """Run the offline checks of one week, quietly. True when they pass."""
    command = [sys.executable, "scripts/lab.py", "check", "--week", str(week)]
    print(f"  running the checks of week {week} ...", file=sys.stderr, flush=True)
    return subprocess.run(command, cwd=ROOT, capture_output=True).returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="also run the offline checks of each item")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()
    results = []
    for number, item in enumerate(ITEMS, start=1):
        try:
            evidence, problems = item.evidence(ROOT)
        except (OSError, ValueError, KeyError) as error:  # a broken file is a failed item, not a crash
            evidence, problems = "a result file", [f"{type(error).__name__}: {error}"]
        state = "fail" if problems else "ok"
        if any("does not exist" in problem for problem in problems):
            state = "missing"
        if args.run and state == "ok":
            failed = [week for week in item.weeks if not run_week(week)]
            if failed:
                state = "fail"
                problems.append(f"The checks of week {', '.join(map(str, failed))} fail.")
        results.append(
            {
                "item": number,
                "text": item.text,
                "evidence": evidence,
                "state": state,
                "problems": problems,
                "questions": item.questions,
                "checks": [f"make check WEEK={week}" for week in item.weeks],
            }
        )
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print_table(results)
    sys.exit(0 if all(result["state"] == "ok" for result in results) else 1)


def print_table(results: list[dict]) -> None:
    for result in results:
        print(f"{result['item']:>2}. [{result['state']:<7}] {result['text']}")
        print(f"    evidence: {result['evidence']}")
        print(f"    proof:    {', '.join(result['checks'])}")
        for problem in result["problems"][:MAX_PROBLEMS]:
            print(f"    - {problem}")
        if len(result["problems"]) > MAX_PROBLEMS:
            print(f"    - and {len(result['problems']) - MAX_PROBLEMS} more (all of them: ARGS=--json)")
    questions = [(result["item"], question) for result in results for question in result["questions"]]
    print("\nOnly you can confirm these:")
    for number, question in questions:
        print(f"{number:>2}. {question}")
    passed = sum(result["state"] == "ok" for result in results)
    print(f"\n{passed} of {len(results)} items are ok.")


if __name__ == "__main__":
    main()
