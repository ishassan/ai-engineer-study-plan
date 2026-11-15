"""Week 7 live check: the real model answers questions about the documents and cites its sources.

Run it with `make check-live WEEK=7`. It sends the first two English and the first
two Arabic questions of evals/retrieval_questions.jsonl through the real loop:
about 12 requests to Claude Haiku 5.5, which cost about $0.01. This number is an
estimate from the size of the requests. Postgres and the two model services must run.
"""

from __future__ import annotations

import json
from pathlib import Path

from labkit.sse import ask

REPO = Path(__file__).resolve().parents[3]


def test_the_answers_cite_chunks_that_the_search_returned(client, live, database, capsys):
    from assistant.retrieval import retrieve

    lines = (REPO / "evals" / "retrieval_questions.jsonl").read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line.strip()]
    chosen = [q for q in questions if q["language"] == "en"][:2] + [q for q in questions if q["language"] == "ar"][:2]
    assert len(chosen) == 4, "Write the retrieval questions of week 5 first."

    rows = []
    for question in chosen:
        result = ask(client, question["question"])
        assert result.status_code == 200
        citations = (result.answer or {}).get("citations", [])
        cited = [citation["chunk_id"] for citation in citations]
        searched = [tool for tool in result.tools if tool["name"] == "search_documents"]
        # A cited chunk must come from a search of this conversation. Run the same searches again.
        returned = {row["chunk_id"] for tool in searched for row in retrieve(tool["input"]["query"], "rerank", 10)}
        rows.append(
            {
                "id": question["id"],
                "searched": bool(searched),
                "cited": cited,
                "cites_expected": bool(set(cited) & set(question["expected_chunk_ids"])),
                "unknown": [chunk_id for chunk_id in cited if chunk_id not in returned],
                "errors": [error["message"] for error in result.errors],
                "requests": result.done["requests"],
                "cost_usd": result.done["cost_usd"],
            }
        )

    with capsys.disabled():
        print()
        for row in rows:
            mark = "expected chunk cited" if row["cites_expected"] else "other chunks cited  "
            print(
                f"  {row['id']:5} {mark}  {len(row['cited'])} citations  {row['requests']} requests"
                f"  ${row['cost_usd']:.5f}  {'; '.join(row['errors'])}"
            )
        print(f"  total cost ${sum(row['cost_usd'] for row in rows):.4f}")
        print("  Write these numbers in phases/phase-2-retrieval/RESULTS.md.")

    assert all(row["searched"] for row in rows), (
        "The model answered a question about a document without search_documents. Say in the "
        "system prompt and in the tool description when to use the tool."
    )
    with_citations = [row for row in rows if row["cited"]]
    assert len(with_citations) >= 3, "At least 3 of the 4 answers must have citations."
    assert not any(row["unknown"] for row in rows), "An answer cites a chunk that no search returned."
    assert sum(row["cites_expected"] for row in rows) >= 2, (
        "Fewer than 2 of the 4 answers cite an expected chunk. Read the tool results: did the "
        "search return the chunk, and did the model use it?"
    )
