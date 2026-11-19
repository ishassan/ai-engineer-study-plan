"""Phase 7: the numbers of the capstone list, the rules of the documents, and the exit test.

`scripts/capstone_numbers.py` prints the numbers, `scripts/exit_test.py` prints the exit test, and
the checks of weeks 26 to 28 use the rules of the documents. Everything here reads files: the
result files of Phases 1 to 6 under `evals/`, and the documents under `docs/`.
"""

from __future__ import annotations

import csv
import json
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
PHASE_DIR = REPO / "phases" / "phase-7-packaging"
TEMPLATES = PHASE_DIR / "starter" / "docs"
ARCHITECTURE = Path("docs/architecture.md")
WRITEUP = Path("docs/writeup.md")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
ARABIC = re.compile(r"[؀-ۿ]")
# A public repository on one of these hosts: https://<host>/<owner>/<repository>.
REPOSITORY_URL = re.compile(
    r"https://(?:www\.)?(github\.com|gitlab\.com|codeberg\.org|bitbucket\.org)/([\w.-]+)/([\w.-]+)"
)


# ---- reading the result files ---------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], fraction: float) -> float:
    """The value below which `fraction` of the values lie (nearest rank), as in Phase 6."""
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def hosted_run(root: Path) -> Path | None:
    """The result file of the newest run of the whole test set on the hosted model.

    First choice: the newest `evals/results/testset-<time>.jsonl` (Phase 3) that has a row for each
    case of `evals/testset.jsonl`. Then `evals/results/models/<route>.jsonl` of Phase 6 for a route
    without a load test (a hosted model) that covers the test set. Then the newest
    `testset-<time>.jsonl`, also when it covers only some cases.
    """
    results = root / "evals" / "results"
    cases_file = root / "evals" / "testset.jsonl"
    ids = {case["id"] for case in read_jsonl(cases_file)} if cases_file.exists() else set()
    runs = sorted(results.glob("testset-*.jsonl"), reverse=True)
    hosted = sorted(
        path for path in results.glob("models/*.jsonl") if not (results / "load" / f"{path.stem}.json").exists()
    )

    def covers(path: Path) -> bool:
        return bool(ids) and ids <= {row.get("id") for row in read_jsonl(path)}

    return next((path for path in runs + hosted if covers(path)), runs[0] if runs else None)


@dataclass
class Number:
    """One number of the capstone list: its value and the file that it comes from."""

    name: str
    value: str
    source: str
    found: bool = True


def _missing(name: str, source: str) -> Number:
    return Number(name, "missing", source, found=False)


def _test_set(root: Path) -> list[Number]:
    path = root / "evals" / "testset.jsonl"
    if not path.exists():
        return [_missing("Test set size", "evals/testset.jsonl")]
    cases = read_jsonl(path)
    arabic = sum(case.get("language") == "ar" for case in cases)
    value = f"{len(cases)} cases ({len(cases) - arabic} English, {arabic} Arabic)"
    return [Number("Test set size", value, relative(path, root))]


def _run_numbers(root: Path) -> list[Number]:
    names = ("Task success rate on the test set", "Groundedness score", "95th-percentile latency", "Cost per request")
    path = hosted_run(root)
    if path is None:
        return [_missing(name, "evals/results/testset-<time>.jsonl") for name in names]
    rows, source = read_jsonl(path), relative(path, root)
    passed = sum(bool(row.get("code_pass")) for row in rows)
    documents = [row for row in rows if row.get("expected_chunk_ids")]
    latencies = [float(row.get("latency_ms") or 0.0) for row in rows]
    cost = sum(float(row.get("cost_usd") or 0.0) for row in rows) / len(rows) if rows else 0.0
    numbers = [Number(names[0], f"{passed / len(rows):.1%} ({passed} of {len(rows)} cases, code_pass)", source)]
    if documents:
        grounded = sum(_grounded(row) for row in documents)
        value = f"{grounded / len(documents):.1%} ({grounded} of {len(documents)} document answers)"
        numbers.append(Number(names[1], value, source))
    else:
        numbers.append(Number(names[1], "missing (the run has no document case)", source, found=False))
    numbers.append(Number(names[2], f"{percentile(latencies, 0.95) / 1000:.2f} s (over {len(rows)} requests)", source))
    numbers.append(Number(names[3], f"${cost:.5f} (mean of {len(rows)} requests)", source))
    return numbers


def _grounded(row: dict[str, Any]) -> bool:
    """A document answer is grounded when it cites a passage, each cited chunk is a stored passage,
    and one cited chunk is an expected chunk of the case."""
    cited = {citation.get("chunk_id") for citation in row.get("citations") or []}
    stored = {passage.get("chunk_id") for passage in row.get("cited_passages") or []}
    return bool(row.get("answer")) and bool(cited) and cited <= stored and bool(cited & set(row["expected_chunk_ids"]))


def _recall(root: Path) -> list[Number]:
    path = root / "evals" / "results" / "recall.json"
    names = {"en": "Retrieval recall, English", "ar": "Retrieval recall, Arabic"}
    if not path.exists():
        return [_missing(name, "evals/results/recall.json") for name in names.values()]
    data = json.loads(path.read_text(encoding="utf-8"))
    numbers = []
    for language, name in names.items():
        questions = len({row["id"] for row in data.get("rows", []) if row.get("language") == language})
        modes = ", ".join(
            f"{mode} {scores[language]:.2f}" for mode, scores in data["recall"].items() if language in scores
        )
        numbers.append(Number(name, f"{modes} (recall@{data.get('k')}, {questions} questions)", relative(path, root)))
    return numbers


def _grader(root: Path) -> list[Number]:
    path = root / "evals" / "grader_agreement.json"
    name = "Grader agreement with your labels"
    if not path.exists():
        return [_missing(name, "evals/grader_agreement.json")]
    data = json.loads(path.read_text(encoding="utf-8"))
    value = (
        f"true positive rate {data['true_positive_rate']:.2f}, true negative rate {data['true_negative_rate']:.2f} "
        f"({len(data.get('rows', []))} labels)"
    )
    return [Number(name, value, relative(path, root))]


def newest_attacks(root: Path) -> Path | None:
    """The newest result file of the attack suite (Phase 5), by its `created` time."""
    files = list((root / "evals" / "results").glob("attacks-*.json"))
    return max(files, key=lambda path: json.loads(path.read_text(encoding="utf-8")).get("created", ""), default=None)


def _attacks(root: Path) -> list[Number]:
    name = "Attack-suite pass rate"
    path = newest_attacks(root)
    if path is None:
        return [_missing(name, "evals/results/attacks-<label>.json")]
    data = json.loads(path.read_text(encoding="utf-8"))
    passed = sum(bool(row.get("passed")) for row in data.get("rows", []))
    value = f"{data['pass_rate']:.1%} ({passed} of {data['cases']} attacks, model {data.get('model')})"
    return [Number(name, value, relative(path, root))]


def comparison_rows(root: Path) -> list[dict[str, str]]:
    path = root / "evals" / "results" / "model_comparison.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _models(root: Path) -> list[Number]:
    columns = {
        "Hosted against self-hosted model: quality": ("quality", "{}"),
        "Hosted against self-hosted model: latency": ("latency_ms_p95", "{} ms p95"),
        "Hosted against self-hosted model: cost": ("cost_per_1000_requests", "${} per 1,000 requests"),
    }
    rows = comparison_rows(root)
    source = "evals/results/model_comparison.csv"
    if not rows:
        return [_missing(name, source) for name in columns]
    return [
        Number(name, ", ".join(f"{row['model']} {form.format(row[column] or '?')}" for row in rows), source)
        for name, (column, form) in columns.items()
    ]


def capstone_numbers(root: Path = REPO) -> list[Number]:
    """Each number of the capstone list, in the order of the templates of docs/."""
    numbers = _test_set(root) + _run_numbers(root) + _recall(root) + _grader(root) + _attacks(root) + _models(root)
    order = [name for name, _, _ in template_table(TEMPLATES / "architecture.md")]
    return sorted(numbers, key=lambda number: order.index(number.name) if number.name in order else len(order))


# ---- the rules of the documents ---------------------------------------------------------------


def strip_comments(text: str) -> str:
    return COMMENT.sub("", text)


def split_sections(text: str) -> tuple[str, dict[str, str]]:
    """The text before the first `## ` heading, and the body of each `## ` section by its heading."""
    head, sections, current = [], {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is None:
            head.append(line)
        else:
            sections[current].append(line)
    return "\n".join(head), {name: "\n".join(lines) for name, lines in sections.items()}


def normalise(text: str) -> str:
    return " ".join(strip_comments(text).split())


def table_rows(text: str) -> list[list[str]]:
    """The rows of the first Markdown table whose header has a column `Source`, without the header."""
    lines = [line.strip() for line in strip_comments(text).splitlines()]
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip("|").split("|")] if line.startswith("|") else []
        if any(cell.lower() == "source" for cell in cells):
            rows = []
            for row in lines[index + 2 :]:
                if not row.startswith("|"):
                    break
                rows.append([cell.strip() for cell in row.strip("|").split("|")])
            return rows
    return []


def template_table(template: Path) -> list[tuple[str, str, str]]:
    return [tuple((row + ["", "", ""])[:3]) for row in table_rows(template.read_text(encoding="utf-8"))]


def source_paths(cell: str) -> list[str]:
    """The paths that a cell of the column Source names: in backticks, or bare words with a `/`."""
    quoted = re.findall(r"`([^`]+)`", cell)
    return quoted or [word.strip(",;") for word in cell.split() if "/" in word]


def tracked_by_git(root: Path, path: str) -> bool | None:
    """True when git tracks the file, False when it does not, None when `root` is not a git work tree."""
    try:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    result = subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=root, capture_output=True, text=True)
    return result.returncode == 0


def table_problems(text: str, template: Path, root: Path, document: str) -> list[str]:
    """Each row of the table of numbers has a value with a digit, and a source file under evals/ that exists."""
    rows = table_rows(text)
    if not rows:
        return [f"{document}: the table of numbers (columns Number, Value, Source) is missing."]
    problems = []
    names = {row[0].strip().lower() for row in rows if row}
    for name, _, _ in template_table(template):
        if name.lower() not in names:
            problems.append(f"{document}: the table has no row `{name}`.")
    for row in rows:
        name, value, source = (row + ["", "", ""])[:3]
        if not re.search(r"\d", value):
            problems.append(f"{document}: the row `{name}` has no number in the column Value.")
        paths = source_paths(source)
        if not paths:
            problems.append(f"{document}: the row `{name}` names no result file in the column Source.")
        for path in paths:
            file = (root / path).resolve()
            inside = file.is_relative_to((root / "evals").resolve())
            if not inside or not file.is_file():
                problems.append(
                    f"{document}: the row `{name}` names `{path}`, which is not a file under evals/ of the project."
                )
    return problems


def document_problems(path: Path, root: Path = REPO, title_must_change: bool = False) -> list[str]:
    """The problems of a document of docs/ against its template: an empty list means that it passes."""
    if not (root / path).exists():
        return [f"{path.as_posix()} does not exist. Run `make start PHASE=7`."]
    text = (root / path).read_text(encoding="utf-8")
    return section_problems(path, root, title_must_change) + table_problems(
        text, TEMPLATES / path.name, root, path.as_posix()
    )


def section_problems(path: Path, root: Path = REPO, title_must_change: bool = False) -> list[str]:
    """Each section of the template is in the document, with text of its own."""
    document = path.as_posix()
    template = TEMPLATES / path.name
    if not (root / path).exists():
        return [f"{document} does not exist. Run `make start PHASE=7`."]
    text = (root / path).read_text(encoding="utf-8")
    template_head, template_sections = split_sections(template.read_text(encoding="utf-8"))
    head, sections = split_sections(text)
    problems = []
    if title_must_change and normalise(head) == normalise(template_head):
        problems.append(f"{document}: the title is still the title of the template.")
    for name, body in template_sections.items():
        if name not in sections:
            problems.append(f"{document}: the section `## {name}` is missing.")
        elif not normalise(sections[name]) or normalise(sections[name]) == normalise(body):
            problems.append(f"{document}: the section `## {name}` holds only the text of the template.")
    return problems


def git_remote(root: Path) -> str | None:
    """The address of the remote `origin` as https://<host>/<owner>/<repository>, or None."""
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    url = result.stdout.strip()
    if result.returncode != 0 or not url:
        return None
    url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    url = re.sub(r"^ssh://git@([^/]+)/", r"https://\1/", url)
    return url.removesuffix(".git").rstrip("/")


def repository_problems(root: Path = REPO) -> list[str]:
    """The write-up names the public repository, and git tracks each result file of its table."""
    path = root / WRITEUP
    if not path.exists():
        return [f"{WRITEUP} does not exist. Run `make start PHASE=7`."]
    text = strip_comments(path.read_text(encoding="utf-8"))
    # A period after the address ends the sentence: it is not part of the name of the repository.
    found = {
        f"https://{host}/{owner}/{name.rstrip('.').removesuffix('.git')}"
        for host, owner, name in REPOSITORY_URL.findall(text)
    }
    if not found:
        return [
            f"{WRITEUP} names no repository. Write its full address, for example "
            "https://github.com/<account>/<repository> (GitHub, GitLab, Codeberg or Bitbucket)."
        ]
    problems = []
    remote = git_remote(root)
    if remote is not None and remote.lower() not in {url.lower() for url in found}:
        problems.append(
            f"{WRITEUP} does not name the repository of this project: `git remote get-url origin` is {remote}."
        )
    for row in table_rows(text):
        for source in source_paths((row + ["", "", ""])[2]):
            if tracked_by_git(root, source) is False:
                problems.append(
                    f"{WRITEUP}: git does not track `{source}`, so the public repository does not have it. "
                    f"evals/results/ is in .gitignore: add the file with `git add -f {source}`."
                )
    return problems


# ---- the exit test -----------------------------------------------------------------------------


@dataclass
class Item:
    """One item of the exit test of the plan."""

    text: str
    evidence: Callable[[Path], tuple[str, list[str]]]
    weeks: list[int] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)


def _files(*paths: str) -> Callable[[Path], list[str]]:
    return lambda root: [f"{path} does not exist." for path in paths if not (root / path).exists()]


def _agent(root: Path) -> tuple[str, list[str]]:
    path = root / "evals" / "results" / "agent-tasks.json"
    if not path.exists():
        return "evals/results/agent-tasks.json", ["evals/results/agent-tasks.json does not exist (make agent-eval)."]
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    tools = {call.get("name") for row in rows for call in row.get("calls", [])}
    multi = sum(len({call.get("name") for call in row.get("calls", [])}) >= 2 for row in rows)
    problems = []
    if len(tools) < 3:
        problems.append(f"The agent tasks used {len(tools)} different tools, not 3 or more.")
    if not multi:
        problems.append("No agent task called two or more different tools.")
    evidence = (
        f"agent-tasks.json: result {data.get('result_score', 0):.2f}, path {data.get('path_score', 0):.2f}, "
        f"{len(tools)} tools, {multi} of {len(rows)} tasks with 2 or more tools"
    )
    return evidence, problems


def _retrieval(root: Path) -> tuple[str, list[str]]:
    numbers = {number.name: number for number in capstone_numbers(root)}
    recall = [numbers["Retrieval recall, English"], numbers["Retrieval recall, Arabic"]]
    grounded = numbers["Groundedness score"]
    problems = [
        f"{number.name}: {number.value} ({number.source})" for number in recall + [grounded] if not number.found
    ]
    run = hosted_run(root)
    if run is not None and not any(row.get("citations") for row in read_jsonl(run)):
        problems.append(f"No answer of {relative(run, root)} cites a source.")
    evidence = f"recall.json; citations in {relative(run, root) if run else 'the test set run'}"
    return evidence, problems


def _testset(root: Path) -> tuple[str, list[str]]:
    path = root / "evals" / "testset.jsonl"
    if not path.exists():
        return "evals/testset.jsonl", ["evals/testset.jsonl does not exist."]
    cases = read_jsonl(path)
    arabic = [case for case in cases if case.get("language") == "ar" or ARABIC.search(case.get("question", ""))]
    problems = [f"The test set has {len(cases)} cases, not 100 or more."] if len(cases) < 100 else []
    problems += ["The test set has no case in Arabic."] if not arabic else []
    return f"evals/testset.jsonl: {len(cases)} cases, {len(arabic)} in Arabic", problems


def _grader_item(root: Path) -> tuple[str, list[str]]:
    problems = _files("evals/rubric.md", "evals/grader_agreement.json")(root)
    number = next(n for n in capstone_numbers(root) if n.name == "Grader agreement with your labels")
    return (
        f"rubric.md; grader_agreement.json: {number.value}" if number.found else "evals/grader_agreement.json"
    ), problems


def _workflow(root: Path) -> str:
    path = root / ".github" / "workflows" / "evals.yml"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _ci(root: Path) -> tuple[str, list[str]]:
    text = _workflow(root)
    if not text:
        return ".github/workflows/evals.yml", [".github/workflows/evals.yml does not exist."]
    problems = [] if "pull_request" in text else ["The workflow does not run on pull_request."]
    problems += (
        [] if ("make evals" in text or "tests/evals" in text) else ["The workflow does not run the suite tests/evals."]
    )
    return ".github/workflows/evals.yml: the suite on each pull request", problems


def _tracing(root: Path) -> tuple[str, list[str]]:
    run = hosted_run(root)
    if run is None:
        return "evals/results/testset-<time>.jsonl", ["No result file of a test set run."]
    rows = read_jsonl(run)
    problems = []
    if not all(re.fullmatch(r"[0-9a-f]{32}", str(row.get("trace_id"))) for row in rows):
        problems.append(f"Some rows of {relative(run, root)} have no trace_id.")
    if not all(float(row.get("latency_ms") or 0) > 0 for row in rows):
        problems.append(f"Some rows of {relative(run, root)} have no latency.")
    numbers = {n.name: n.value for n in capstone_numbers(root)}
    evidence = f"{relative(run, root)}: p95 {numbers['95th-percentile latency']}, cost {numbers['Cost per request']}"
    return evidence, problems


def _migrations(root: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted((root / "db" / "migrations").glob("*.sql")))


def _permissions(root: Path) -> tuple[str, list[str]]:
    problems = (
        []
        if re.search(r"ENABLE ROW LEVEL SECURITY", _migrations(root), re.IGNORECASE)
        else ["No migration of db/migrations turns on row security."]
    )
    problems += _files("assistant/auth.py")(root)
    return "row security in db/migrations, assistant/auth.py", problems


def _approval(root: Path) -> tuple[str, list[str]]:
    graph = root / "assistant" / "graph.py"
    text = graph.read_text(encoding="utf-8") if graph.exists() else ""
    problems = [] if "interrupt(" in text else ["assistant/graph.py does not call interrupt() before a write action."]
    problems += (
        [] if re.search(r"\baudit", _migrations(root), re.IGNORECASE) else ["No migration makes an audit table."]
    )
    return "interrupt() in assistant/graph.py, the audit table of db/migrations", problems


def _attack_item(root: Path) -> tuple[str, list[str]]:
    number = next(n for n in capstone_numbers(root) if n.name == "Attack-suite pass rate")
    problems = [] if number.found else [f"{number.source} does not exist (make attacks)."]
    problems += [] if "attack" in _workflow(root) else ["The workflow does not run the attack suite."]
    return (f"{number.source}: {number.value}; the suite in the workflow" if number.found else number.source), problems


def _open_model(root: Path) -> tuple[str, list[str]]:
    rows = comparison_rows(root)
    if not rows:
        return "evals/results/model_comparison.csv", ["evals/results/model_comparison.csv does not exist."]
    hosted = [row for row in rows if row.get("cost_basis") == "tokens"]
    open_models = [row for row in rows if row.get("cost_basis") == "GPU hour"]
    problems = [] if hosted and open_models else ["The table needs a hosted model and an open model."]
    for row in rows:
        empty = [column for column in ("quality", "latency_ms_p95", "cost_per_1000_requests") if not row.get(column)]
        problems += [f"{row['model']} has no {', '.join(empty)}."] if empty else []
    return f"model_comparison.csv: {', '.join(row['model'] for row in rows)}", problems


def _architecture(root: Path) -> tuple[str, list[str]]:
    return str(ARCHITECTURE), document_problems(ARCHITECTURE, root)


def _public(root: Path) -> tuple[str, list[str]]:
    problems = document_problems(WRITEUP, root, title_must_change=True) + repository_problems(root)
    return f"{WRITEUP} names the repository", problems


ITEMS = [
    Item(
        "An agent with at least three tools completes multi-step tasks for real users.",
        _agent,
        [16],
        ["Who are the real users (a team, a number of people), and where is the evidence?"],
    ),
    Item("Answers drawn from documents cite their sources, and retrieval quality is measured.", _retrieval, [6, 7]),
    Item("A test set of 100 or more cases exists, including cases in Arabic.", _testset, [9]),
    Item(
        "A grader model scores outputs against a written rubric, and its agreement with your own labels is measured.",
        _grader_item,
        [10],
    ),
    Item(
        "A pipeline blocks any change that lowers the test scores.",
        _ci,
        [11],
        ["Which pull request shows the job `evals` failing on a bad change (Phase 3 RESULTS.md)?"],
    ),
    Item("Every request is traced, with cost and latency reported per request.", _tracing, [8, 26]),
    Item("A tool server enforces each user's permissions before any data reaches the model.", _permissions, [19]),
    Item("Write actions cannot run without human approval, and every action is logged.", _approval, [15, 19]),
    Item("A prompt-injection test suite runs on every change, and its pass rate is reported.", _attack_item, [18, 20]),
    Item(
        "The same system runs on a self-hosted open model, compared with the hosted one on quality, latency and cost.",
        _open_model,
        [25],
    ),
    Item(
        "An architecture document explains each choice, including where plain code replaced a model call.",
        _architecture,
        [26],
    ),
    Item(
        "The code and results are public, and your CV quotes the numbers.",
        _public,
        [27],
        [
            "Is the repository public? Open its address in a browser where you are signed out.",
            "Does your CV quote the numbers of docs/writeup.md, with the same values?",
        ],
    ),
]
