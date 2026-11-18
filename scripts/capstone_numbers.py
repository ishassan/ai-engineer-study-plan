"""Print each number of the capstone list, with the result file that it comes from. Phase 7.

    make numbers                     a table on the screen
    make numbers ARGS=--markdown     the rows for the tables of docs/architecture.md and docs/writeup.md

The numbers come from the result files of Phases 1 to 6 under evals/. A number whose file does not
exist is printed as "missing". The rules of each number are in labkit/capstone.py.

The name is not numbers.py, because a script with that name hides the module `numbers` of the
Python standard library.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # for the package labkit

from labkit.capstone import capstone_numbers  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markdown", action="store_true", help="print the rows of a Markdown table")
    args = parser.parse_args()
    numbers = capstone_numbers(ROOT)
    if args.markdown:
        print("| Number | Value | Source |\n| --- | --- | --- |")
        for number in numbers:
            print(f"| {number.name} | {number.value} | `{number.source}` |")
        return
    width = max(len(number.name) for number in numbers)
    for number in numbers:
        print(f"{number.name:<{width}}  {number.value}\n{'':<{width}}  from {number.source}")


if __name__ == "__main__":
    main()
