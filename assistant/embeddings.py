"""The client of the embedding service and the re-ranking service. This file is complete.

Docker Compose runs two copies of Hugging Face Text Embeddings Inference:

    embeddings   BAAI/bge-m3              POST /embed    one vector of 1024 numbers for each text
    reranker     BAAI/bge-reranker-v2-m3  POST /rerank   one score for each (query, text) pair

Both models run on the CPU of your machine. No request leaves your machine and no
request costs money.

BGE-M3 uses the same call for a query and for a document: you add no instruction
text. The vectors have a length of 1, so the inner product of two vectors is their
cosine similarity.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# The size of one vector of BAAI/bge-m3.
EMBEDDING_DIMENSIONS = 1024
# The services accept at most 32 texts in one request (--max-client-batch-size).
BATCH_SIZE = 32
# One batch can take more than a minute on a slow CPU.
TIMEOUT_SECONDS = 600


def embeddings_url() -> str:
    return os.environ.get("EMBEDDINGS_URL", "http://localhost:8081").rstrip("/")


def reranker_url() -> str:
    return os.environ.get("RERANKER_URL", "http://localhost:8082").rstrip("/")


def _post(url: str, body: dict[str, Any]) -> Any:
    try:
        response = httpx.post(url, json=body, timeout=TIMEOUT_SECONDS)
    except httpx.TransportError as error:
        raise RuntimeError(
            f"The service at {url} does not answer. Start it with `make up` and wait until "
            f"the model is loaded.\n{type(error).__name__}: {error}"
        ) from error
    if response.status_code != 200:
        raise RuntimeError(f"{url} answered {response.status_code}: {response.text[:500]}")
    return response.json()


def embed(texts: list[str]) -> list[list[float]]:
    """Return one vector for each text, in the same order.

    The function sends the texts in batches of 32. A text of more than 2048
    tokens is cut at 2048 tokens (the limit is in compose.yaml).
    """
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        body = {"inputs": batch, "normalize": True, "truncate": True}
        vectors.extend(_post(f"{embeddings_url()}/embed", body))
    return vectors


def rerank(query: str, texts: list[str]) -> list[float]:
    """Return one relevance score for each text, in the same order as `texts`.

    A score is between 0 and 1, and a higher score means that the text answers
    the query better. The model reads the query and one text together, so it is
    slower than a vector search: give it only the best candidates.
    """
    scores = [0.0] * len(texts)
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        body = {"query": query, "texts": batch, "truncate": True}
        for item in _post(f"{reranker_url()}/rerank", body):
            scores[start + item["index"]] = item["score"]
    return scores
