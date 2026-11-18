"""Week 27 checks: the public write-up.

Run them with `make check WEEK=27`. They read docs/writeup.md and the result files under evals/,
so they need no service. The CV is not in the repository, so no check reads it: the exit test asks
you about it.

Fixed names:

- `docs/writeup.md` keeps the sections of its template and the table of numbers (columns Number,
  Value, Source). The title is your own.
- The write-up names the repository with its full address, https://<host>/<account>/<repository>,
  on GitHub, GitLab, Codeberg or Bitbucket. When the project has a git remote `origin`, it is that
  repository.
- Each source of the table is a file under evals/ that exists. When the project is a git
  repository, git tracks each of these files, so the public repository has them.
"""

from __future__ import annotations

from labkit.capstone import REPO, TEMPLATES, WRITEUP, repository_problems, section_problems, table_problems


def report(problems: list[str]) -> str:
    return "docs/writeup.md is not complete:\n- " + "\n- ".join(problems)


def test_each_section_of_the_writeup_is_written():
    problems = section_problems(WRITEUP, REPO, title_must_change=True)
    assert not problems, report(problems)


def test_each_number_of_the_writeup_names_its_result_file():
    path = REPO / WRITEUP
    assert path.exists(), "docs/writeup.md does not exist. Run `make start PHASE=7`."
    problems = table_problems(path.read_text(encoding="utf-8"), TEMPLATES / "writeup.md", REPO, WRITEUP.as_posix())
    assert not problems, report(problems)


def test_the_writeup_names_the_public_repository():
    problems = repository_problems(REPO)
    assert not problems, report(problems)
