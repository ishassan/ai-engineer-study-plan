"""Reference solution."""

from __future__ import annotations

from typing import Any

from assistant.db import query
from assistant.embeddings import embed, rerank
from assistant.ingest import normalise_arabic, vector_literal

CANDIDATES = 20
MODES = ("vector", "hybrid", "rerank")

COLUMNS = "c.id AS chunk_id, c.document_id, d.title, c.language, c.page, c.text"

VECTOR_SQL = f"""
SELECT {COLUMNS}, 1 - c.distance AS score
FROM (
    SELECT *, embedding <=> %(vector)s::vector AS distance
    FROM chunks
    ORDER BY embedding <=> %(vector)s::vector
    LIMIT %(k)s
) c
JOIN documents d ON d.id = c.document_id
ORDER BY c.distance, c.id
"""

# plainto_tsquery joins the words with AND. A question has many words, so the query uses OR:
# a chunk matches when it holds one word, and ts_rank_cd puts the chunks with more words first.
KEYWORD_SQL = f"""
WITH q AS (
    SELECT NULLIF(replace(plainto_tsquery('arabic', %(query)s)::text, '&', '|'), '')::tsquery AS ar,
           NULLIF(replace(plainto_tsquery('english', %(query)s)::text, '&', '|'), '')::tsquery AS en
), matches AS (
    SELECT c.id, ts_rank_cd(c.tsv, q.ar, 32) AS score FROM chunks c, q
    WHERE c.language = 'ar' AND c.tsv @@ q.ar
    UNION ALL
    SELECT c.id, ts_rank_cd(c.tsv, q.en, 32) AS score FROM chunks c, q
    WHERE c.language = 'en' AND c.tsv @@ q.en
)
SELECT {COLUMNS}, m.score
FROM matches m
JOIN chunks c ON c.id = m.id
JOIN documents d ON d.id = c.document_id
ORDER BY m.score DESC, c.id
LIMIT %(k)s
"""


def vector_search(query_text: str, k: int = 5) -> list[dict[str, Any]]:
    vector = embed([normalise_arabic(query_text)])[0]
    return query(VECTOR_SQL, {"vector": vector_literal(vector), "k": k})


def keyword_search(query_text: str, k: int = 5) -> list[dict[str, Any]]:
    return query(KEYWORD_SQL, {"query": normalise_arabic(query_text), "k": k})


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def _hybrid(query_text: str, k: int) -> list[dict[str, Any]]:
    by_vector = vector_search(query_text, CANDIDATES)
    by_keyword = keyword_search(query_text, CANDIDATES)
    rows = {row["chunk_id"]: row for row in by_keyword + by_vector}
    fused = reciprocal_rank_fusion(
        [[row["chunk_id"] for row in by_vector], [row["chunk_id"] for row in by_keyword]]
    )
    return [dict(rows[chunk_id], score=score) for chunk_id, score in fused[:k]]


def retrieve(query_text: str, mode: str = "rerank", k: int = 5) -> list[dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}. Use one of {', '.join(MODES)}.")
    if mode == "vector":
        return vector_search(query_text, k)
    if mode == "hybrid":
        return _hybrid(query_text, k)
    candidates = _hybrid(query_text, CANDIDATES)
    if not candidates:
        return []
    scores = rerank(normalise_arabic(query_text), [row["text"] for row in candidates])
    ranked = sorted(zip(scores, candidates), key=lambda pair: (-pair[0], pair[1]["chunk_id"]))
    return [dict(row, score=score) for score, row in ranked[:k]]
