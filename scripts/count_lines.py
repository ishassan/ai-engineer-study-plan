"""Count the lines of code of the hand-written loop and of the graph. Phase 4, week 14.

    make lines

A line of code is a line that is not empty, not a comment and not part of a docstring.
The files of each loop are in the lists below. Change the lists when your files differ.
The shared files (tools, retrieval, memory, conversations) serve both loops, so the
script counts them apart.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS = {
    "hand-written loop": ["assistant/agent.py", "assistant/llm.py", "assistant/planner.py"],
    "LangGraph graph": ["assistant/graph.py", "assistant/models.py"],
    "shared by both": [
        "assistant/tools.py",
        "assistant/retrieval.py",
        "assistant/memory.py",
        "assistant/conversations.py",
        "assistant/schemas.py",
    ],
}


def docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                if isinstance(body[0].value.value, str):
                    lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    return lines


def code_lines(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    skip = docstring_lines(ast.parse(source))
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                          tokenize.ENDMARKER}:
            continue
        for line in range(token.start[0], token.end[0] + 1):
            if line not in skip:
                lines.add(line)
    return len(lines)


def main() -> None:
    for group, files in GROUPS.items():
        total = 0
        print(group)
        for name in files:
            path = ROOT / name
            if not path.exists():
                print(f"  {name:32} (missing)")
                continue
            count = code_lines(path)
            total += count
            print(f"  {name:32} {count:5}")
        print(f"  {'total':32} {total:5}\n")


if __name__ == "__main__":
    main()
