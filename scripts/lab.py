"""Lab commands: copy the starter files of a phase, and run the checks of a week.

The Makefile calls this script:

    make start PHASE=1
    make check WEEK=2
    make check-live WEEK=2
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The phases that you started, one number on each line. The Makefile reads this file to
# install the Python packages and to start the Docker services of these phases.
STARTED = ROOT / ".lab-phases"
# The first and the last week of each phase.
PHASE_WEEKS = {1: (1, 3), 2: (4, 7), 3: (8, 11), 4: (12, 17), 5: (18, 20), 6: (21, 25), 7: (26, 28)}


def phase_dir(phase: int) -> Path:
    matches = sorted((ROOT / "phases").glob(f"phase-{phase}-*"))
    if not matches:
        sys.exit(f"There is no folder for phase {phase} in phases/.")
    return matches[0]


def phase_of_week(week: int) -> int:
    for phase, (first, last) in PHASE_WEEKS.items():
        if first <= week <= last:
            return phase
    sys.exit(f"Week {week} is not in the plan. The plan has weeks 1 to 28.")


def start(phase: int) -> None:
    """Copy each starter file into the project, and keep each file that exists."""
    starter = phase_dir(phase) / "starter"
    started = {int(line) for line in STARTED.read_text().split()} if STARTED.exists() else set()
    STARTED.write_text("".join(f"{number}\n" for number in sorted(started | {phase})))
    if not starter.is_dir():
        print(f"Phase {phase} has no starter files. Open {phase_dir(phase).name}/README.md.")
        return
    created, kept = [], []
    for source in sorted(path for path in starter.rglob("*") if path.is_file()):
        relative = source.relative_to(starter)
        target = ROOT / relative
        if target.exists():
            kept.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(relative)
    for relative in created:
        print(f"created  {relative}")
    for relative in kept:
        print(f"kept     {relative} (the file exists, so it was not changed)")
    print(f"\nNext: open {phase_dir(phase).relative_to(ROOT)}/README.md")


def check(week: int | None, phase: int | None, live: bool) -> None:
    suffix = "_live.py" if live else ".py"
    if week is not None:
        checks = phase_dir(phase_of_week(week)) / "checks"
        files = [checks / f"test_week{week}{suffix}"]
    elif phase is not None:
        first, last = PHASE_WEEKS[phase]
        checks = phase_dir(phase) / "checks"
        files = [checks / f"test_week{n}{suffix}" for n in range(first, last + 1)]
    else:
        sys.exit("Give a week or a phase, for example: make check WEEK=1")
    files = [path for path in files if path.exists()]
    if not files:
        kind = "live" if live else "offline"
        sys.exit(f"There is no {kind} check for this week.")
    command = [sys.executable, "-m", "pytest", *map(str, files)]
    if live:
        command.append("--live")
    sys.exit(subprocess.call(command, cwd=ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("phase", type=int, choices=sorted(PHASE_WEEKS))
    check_parser = commands.add_parser("check")
    check_parser.add_argument("--week", type=int)
    check_parser.add_argument("--phase", type=int, choices=sorted(PHASE_WEEKS))
    check_parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.command == "start":
        start(args.phase)
    else:
        check(args.week, args.phase, args.live)


if __name__ == "__main__":
    main()
