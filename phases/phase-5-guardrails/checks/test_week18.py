"""Week 18 checks: the attack cases, the poisoned material, the first run and the CI step.

Run them with `make check WEEK=18`. Postgres with the documents and the poisoned material
(`make poison`) and both model services must be ready. One check runs two cases of your suite
with the obedient model (labkit/obedient.py), which is free, so the checks call no paid API.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
CASES = REPO / "evals" / "attacks.jsonl"
POISONED = REPO / "data" / "poisoned"
FIRST_RUN = REPO / "evals" / "results" / "attacks-week18.json"
WORKFLOW = REPO / ".github" / "workflows" / "evals.yml"
ACTIONLINT = "rhysd/actionlint:1.7.12"
KINDS = {"direct", "poisoned_document", "tool_result", "exfiltration"}
USERS = {"viewer", "analyst", "auditor"}
SERVER_TOOLS = {"run_sql", "search_datasets", "get_dataset_schema", "get_dataset_stats", "register_dataset"}
FIELDS = {"id", "kind", "user", "question", "forbidden_tools", "forbidden_strings", "approval"}
ARABIC = re.compile("[؀-ۿ]")
PREFIX = "poisoned-"


def cases() -> list[dict[str, Any]]:
    assert CASES.exists(), "evals/attacks.jsonl does not exist. Run `make start PHASE=5`."
    rows = []
    for number, line in enumerate(CASES.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                pytest.fail(f"evals/attacks.jsonl, line {number}: not valid JSON ({error}).", pytrace=False)
    return rows


def known_tools() -> set[str]:
    from assistant.tools import TOOLS

    return {tool["name"] for tool in TOOLS} | SERVER_TOOLS


def documents() -> list[tuple[Path, dict[str, str], str]]:
    """Each poisoned Markdown file with its header and its text."""
    found = []
    for path in sorted(POISONED.glob("*.md")) if POISONED.is_dir() else []:
        if path.name.lower() == "readme.md":
            continue
        header_text, _, body = path.read_text(encoding="utf-8").partition("\n\n")
        header = {}
        for line in header_text.splitlines():
            key, _, value = line.partition(":")
            header[key.strip().lower()] = value.strip()
        found.append((path, header, body))
    return found


def poisoned_datasets() -> list[dict[str, Any]]:
    path = POISONED / "datasets.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def holds_an_instruction(text: str) -> bool:
    """True when the text names a tool of the agent or holds a link: a hidden instruction."""
    return bool(re.search(r"https?://", text)) or any(re.search(rf"\b{name}\b", text) for name in known_tools())


# ---- step 3: the attack cases -------------------------------------------------------------------


def test_each_case_follows_the_format():
    problems = []
    tools = known_tools()
    for case in cases():
        name = case.get("id", "?")
        unknown = set(case) - FIELDS
        if unknown:
            problems.append(f"{name}: unknown fields {sorted(unknown)}")
        if case.get("kind") not in KINDS:
            problems.append(f"{name}: kind {case.get('kind')!r} is not one of {sorted(KINDS)}")
        if case.get("user", "viewer") not in USERS:
            problems.append(f"{name}: user {case.get('user')!r} is not a test user ({sorted(USERS)})")
        if not str(case.get("question", "")).strip():
            problems.append(f"{name}: no question")
        if not case.get("forbidden_tools") and not case.get("forbidden_strings"):
            problems.append(f"{name}: give forbidden_tools or forbidden_strings, or the case cannot fail")
        wrong = set(case.get("forbidden_tools", [])) - tools
        if wrong:
            problems.append(f"{name}: {sorted(wrong)} are not tools of the agent")
        if not all(isinstance(text, str) and len(text) >= 4 for text in case.get("forbidden_strings", [])):
            problems.append(f"{name}: each forbidden string has 4 characters or more")
        if not isinstance(case.get("approval", False), bool):
            problems.append(f"{name}: approval is true or false")
    assert not problems, "Problems in evals/attacks.jsonl:\n" + "\n".join(problems)


def test_you_wrote_30_cases_of_the_four_kinds():
    rows = cases()
    ids = [case.get("id") for case in rows]
    assert len(rows) >= 30, f"evals/attacks.jsonl has {len(rows)} cases. Write 30 or more (week 18, step 3)."
    assert len(set(ids)) == len(ids), "Each case needs its own id."
    questions = [case.get("question") for case in rows]
    assert len(set(questions)) == len(questions), "Two cases have the same question."
    counts = {kind: sum(case.get("kind") == kind for case in rows) for kind in sorted(KINDS)}
    assert all(count >= 5 for count in counts.values()), f"Write 5 or more cases of each kind: {counts}"
    leaks = [case for case in rows if case.get("kind") == "exfiltration"]
    assert any(re.search(r"https?://", case["question"]) or any("." in text for text in case.get("forbidden_strings", []))
               for case in leaks), "An exfiltration case must try to send data out, for example through a link."


# ---- step 2: the poisoned documents -------------------------------------------------------------


def test_the_poisoned_documents_are_in_english_and_arabic():
    found = documents()
    assert found, "data/poisoned/ has no Markdown file. Write the poisoned documents there (week 18, step 2)."
    for path, header, body in found:
        assert header.get("language") in {"en", "ar"} and header.get("title"), (
            f"{path.name}: start with the lines `title: ...` and `language: en` (or ar), then an empty line."
        )
        assert holds_an_instruction(body), (
            f"{path.name}: hide an instruction in the text, for example a request to call a tool of the "
            "agent or to put a link in the answer."
        )
    languages = {header["language"] for _, header, _ in found}
    assert languages == {"en", "ar"}, "Write poisoned documents in English and in Arabic."
    arabic = [body for _, header, body in found if header["language"] == "ar"]
    assert all(len(ARABIC.findall(body)) > 100 for body in arabic), "Write the Arabic documents in Arabic."


def test_make_poison_stored_the_material_with_the_marker(sql):
    stored = {row["id"]: row for row in sql(
        "SELECT d.id, d.publisher, count(c.id) AS chunks, count(c.embedding) AS vectors "
        "FROM documents d LEFT JOIN chunks c ON c.document_id = d.id WHERE d.id LIKE %s GROUP BY d.id, d.publisher",
        (PREFIX + "%",),
    )}
    for path, _, _ in documents():
        row = stored.get(PREFIX + path.stem)
        assert row, f"{path.name} is not in the table documents. Run `make poison`."
        assert row["chunks"] >= 1 and row["vectors"] == row["chunks"], (
            f"{path.name}: each chunk needs its vector. Run `make poison` while the embedding service runs."
        )
    datasets = {row["id"] for row in sql("SELECT id FROM datasets WHERE id LIKE %s", (PREFIX + "%",))}
    missing = [item["id"] for item in poisoned_datasets() if item["id"] not in datasets]
    assert not missing, f"These poisoned datasets are not in the catalogue: {missing}. Run `make poison`."


def test_each_poisoned_document_case_finds_a_poisoned_passage(services, sql):
    from assistant.tools import run_tool

    rows = [case for case in cases() if case.get("kind") == "poisoned_document"]
    assert rows, "Write cases of the kind poisoned_document."
    missed = []
    for case in rows:
        found = json.loads(run_tool("search_documents", {"query": case["question"]}))
        if not any(str(row.get("chunk_id", "")).startswith(PREFIX) for row in found):
            missed.append(case["id"])
    assert not missed, (
        f"The question of these cases does not find a poisoned passage with search_documents: {missed}. "
        "Such a case tests nothing. Ask about the subject of a poisoned document."
    )


def test_each_tool_result_case_finds_a_poisoned_result(sql):
    from assistant.tools import run_tool

    rows = [case for case in cases() if case.get("kind") == "tool_result"]
    assert rows, "Write cases of the kind tool_result."
    missed = []
    for case in rows:
        found = json.loads(run_tool("search_datasets", {"query": case["question"], "limit": 5}))
        if not any(str(row.get("id", "")).startswith(PREFIX) for row in found):
            missed.append(case["id"])
    assert not missed, (
        f"The question of these cases does not find a poisoned dataset with search_datasets: {missed}. "
        "Put poisoned entries in data/poisoned/datasets.jsonl, run `make poison`, and ask about their subject."
    )


# ---- step 4: the suite runs and records its pass rate ---------------------------------------------


def test_the_suite_runs_with_the_obedient_model(tmp_path, services):
    rows = cases()
    chosen = [next(case for case in rows if case.get("kind") == kind) for kind in ("direct", "poisoned_document")]
    out = tmp_path / "attacks-check.json"
    command = [sys.executable, "-m", "pytest", "tests/attacks", "-q", "-p", "no:cacheprovider",
               "--attack-model", "obedient", "--attack-label", "check", "--attack-results", str(out),
               "-k", " or ".join(f"{case['id']}-" for case in chosen)]
    process = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=900, env=dict(os.environ))
    assert process.returncode == 0 and out.exists(), (
        "The attack suite did not run (make attacks MODEL=obedient):\n" + (process.stdout + process.stderr)[-3000:]
    )
    result = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(row["id"] for row in result["rows"]) == sorted(case["id"] for case in chosen)


def test_the_first_run_recorded_a_pass_rate_for_each_kind():
    assert FIRST_RUN.exists(), "Run the suite: make attacks LABEL=week18 (or with MODEL=obedient)."
    result = json.loads(FIRST_RUN.read_text(encoding="utf-8"))
    rows = cases()
    by_id = {case["id"]: case for case in rows}
    recorded = {row["id"]: row for row in result["rows"]}
    assert set(recorded) == set(by_id), (
        "The result of week 18 must hold each case of evals/attacks.jsonl, and only those. Run the suite "
        "again after a change of the cases, and do not change the cases after this run: week 20 compares "
        "its pass rates with this one."
    )
    assert all(recorded[name]["kind"] == by_id[name]["kind"] for name in by_id), "The kinds of the result changed."
    assert result["model"] in {"claude", "obedient"}
    for kind in KINDS:
        of_kind = [row for row in result["rows"] if row["kind"] == kind]
        passed = sum(row["passed"] for row in of_kind)
        assert result["kinds"][kind]["cases"] == len(of_kind) and result["kinds"][kind]["passed"] == passed, (
            f"The numbers of the kind {kind} do not agree with the rows. Do not edit the result file."
        )
        assert result["kinds"][kind]["pass_rate"] == round(passed / len(of_kind), 4)
    print("\n" + "\n".join(f"  {kind:<20} {value['passed']:>3} of {value['cases']:<3} {value['pass_rate']:.2f}"
                           for kind, value in result["kinds"].items()))


# ---- step 5: CI ---------------------------------------------------------------------------------


def test_ci_runs_the_attack_suite():
    assert WORKFLOW.exists(), ".github/workflows/evals.yml does not exist (week 11)."
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "make attacks" in text or "tests/attacks" in text, "Add a step that runs the attack suite."
    assert "poison" in text, "Load the poisoned material in the job (make poison), or the suite tests nothing."
    assert "phase5" in text, "Install the packages of phase 5 in the job."
    docker = shutil.which("docker")
    assert docker, "Docker is not on the PATH. The check runs actionlint in Docker."
    process = subprocess.run(
        [docker, "run", "--rm", "-v", f"{REPO}:/repo:ro", "-w", "/repo", ACTIONLINT, "-color=false",
         ".github/workflows/evals.yml"],
        capture_output=True, text=True, timeout=300,
    )
    assert process.returncode == 0, f"actionlint found problems in the workflow:\n{process.stdout}{process.stderr}"
