"""Search the chunks. Weeks 5 and 6.

Each search function returns a list of dicts, with the best result first. One
result has these keys:

    chunk_id      the id of the chunk, for example gastat-land-transport-en:p7:c2
    document_id   the id of the document
    title         the title of the document
    language      "ar" or "en"
    page          the page number in the document
    text          the text of the chunk
    score         a number that is higher for a better result

Normalise each query with normalise_arabic() from assistant/ingest.py before
you embed it or search with it.
"""

from __future__ import annotations

from typing import Any

from assistant.db import query  # noqa: F401 (you will use it)
from assistant.embeddings import embed, rerank  # noqa: F401 (you will use them)

# The number of results that the vector search and the keyword search each give to the
# rank fusion, and the number of fused results that the re-ranking model reads.
CANDIDATES = 20


def vector_search(query_text: str, k: int = 5) -> list[dict[str, Any]]:
    """Return the k chunks whose vectors are nearest to the vector of the query."""
    raise NotImplementedError("Week 5, step 2")


def keyword_search(query_text: str, k: int = 5) -> list[dict[str, Any]]:
    """Return the k chunks that match the words of the query best, with Postgres text search."""
    raise NotImplementedError("Week 6, step 2")


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Merge ranked lists of ids into one list of (id, score), with the best id first.

    The score of an id is the sum of 1 / (k + rank) over the lists that hold the
    id. The rank of the first id of a list is 1.
    """
    raise NotImplementedError("Week 6, step 3")


def retrieve(query_text: str, mode: str = "rerank", k: int = 5) -> list[dict[str, Any]]:
    """Return the k best chunks for a query. This is the one entry point for all callers.

    mode "vector"   the vector search alone (week 5)
    mode "hybrid"   the top 20 of the vector search and the top 20 of the keyword
                    search, merged with reciprocal rank fusion (week 6)
    mode "rerank"   the top 20 of the hybrid search, put in a new order with
                    rerank() from assistant/embeddings.py (week 6)

    Raise a ValueError for any other mode.
    """
    raise NotImplementedError("Week 5, step 2, and week 6, step 3")
