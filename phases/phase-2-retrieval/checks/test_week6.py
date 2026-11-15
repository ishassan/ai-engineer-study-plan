"""Week 6 checks: the keyword search, reciprocal rank fusion, re-ranking and the
recall table.

Run them with `make check WEEK=6`. They are free. Postgres, the embedding service
and the re-ranking service must run on your machine (`make up`). The re-ranking
model is slow on a CPU, so the checks take some minutes. The last check reads the
file that `make recall` writes.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from test_week5 import RESULT_KEYS, excerpt, read_recall_file, sample_chunks

ENGLISH_QUERY = "Which administrative records are the source of the transport statistics?"
ARABIC_QUERY = "ما هي مصادر بيانات إحصاءات النقل البري؟"


def with_marks(text: str) -> str:
    """Put a tatweel in each word of four letters or more, and a fatha after the first letter."""
    words = []
    for word in text.split():
        if len(word) >= 4 and word.isalpha():
            word = word[0] + "\u064e" + word[1:2] + "\u0640\u0640" + word[2:]
        words.append(word)
    return " ".join(words)


# ---- step 2: the keyword search ---------------------------------------------------------


def test_the_chunks_have_a_text_search_column_with_a_gin_index(chunks, sql):
    columns = sql(
        "SELECT attname FROM pg_attribute WHERE attrelid = 'chunks'::regclass AND attnum > 0 "
        "AND NOT attisdropped AND format_type(atttypid, atttypmod) = 'tsvector'"
    )
    assert columns, (
        "The table chunks has no column of the type tsvector. Write a migration file that adds "
        "one, then run `make up`."
    )
    names = [column["attname"] for column in columns]
    indexes = sql("SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks'")
    assert any(
        "using gin" in index["indexdef"].lower() and any(name in index["indexdef"] for name in names)
        for index in indexes
    ), f"The text-search column {names[0]} has no GIN index."
    empty = sql(f'SELECT count(*) AS n FROM chunks WHERE "{names[0]}" IS NULL OR "{names[0]}" = \'\'')[0]["n"]
    assert empty < 0.01 * chunks, f"{empty} chunks have an empty text-search column."


@pytest.mark.parametrize("language", ["en", "ar"])
def test_keyword_search_finds_a_chunk_from_some_of_its_words(language, chunks, sql):
    from assistant.retrieval import keyword_search

    for chunk in sample_chunks(sql, language, 3):
        query = excerpt(chunk["text"], 20, 45)
        results = keyword_search(query, 5)
        assert results, f"keyword_search returns nothing for 25 words of the chunk {chunk['id']}."
        assert RESULT_KEYS <= set(results[0])
        assert [r for r in results if query in r["text"]], (
            f"A keyword search with 25 words of the chunk {chunk['id']} does not return this "
            f"chunk in the top 5. For Arabic, test the text search configuration that you use."
        )
        scores = [result["score"] for result in results]
        assert scores == sorted(scores, reverse=True)


def test_keyword_search_normalises_the_arabic_query(chunks, sql):
    from assistant.retrieval import keyword_search

    chunk = sample_chunks(sql, "ar", 1)[0]
    query = excerpt(chunk["text"], 20, 45)
    plain = [result["chunk_id"] for result in keyword_search(query, 5)]
    marked = [result["chunk_id"] for result in keyword_search(with_marks(query), 5)]
    assert marked == plain, (
        "The same Arabic words with diacritics and tatweel give other results. Normalise the "
        "query with normalise_arabic() before the search."
    )


def test_the_arabic_query_has_the_configuration_of_the_column(chunks, sql):
    from assistant.retrieval import keyword_search

    column = sql(
        "SELECT attname FROM pg_attribute WHERE attrelid = 'chunks'::regclass AND attnum > 0 "
        "AND NOT attisdropped AND format_type(atttypid, atttypmod) = 'tsvector'"
    )[0]["attname"]
    tested = found = 0
    for chunk in sample_chunks(sql, "ar", 3):
        stored = sql(f'SELECT "{column}"::text AS lexemes FROM chunks WHERE id = %s', (chunk["id"],))[0]
        lexemes = set(re.findall(r"'([^']*)'", stored["lexemes"]))
        # The words that the configuration of the column changed, for example الجدول to جدول.
        changed = [word for word in chunk["text"].split()[5:65] if word.isalpha() and word.lower() not in lexemes]
        if len(changed) < 10:
            continue  # The configuration keeps the words as they are, for example `simple`.
        tested += 1
        results = keyword_search(" ".join(dict.fromkeys(changed)), 20)
        found += chunk["id"] in [result["chunk_id"] for result in results]
    assert found >= min(tested, 2), (
        "A query with words of an Arabic chunk does not find the chunk. The query gives other "
        "lexemes than the text-search column: use the same text search configuration for the "
        "column and for the query of each language."
    )


def test_keyword_search_returns_an_empty_list_when_no_word_matches(chunks):
    from assistant.retrieval import keyword_search

    assert keyword_search("zzqqxv wwkkyq", 5) == []


def test_a_question_matches_when_only_some_of_its_words_are_in_a_chunk(chunks):
    from assistant.retrieval import keyword_search

    assert keyword_search(ENGLISH_QUERY + " zzqqxv", 5), (
        "A question holds words that no chunk has. If the search needs each word of the query, "
        "a full question finds nothing. Accept a chunk that matches some of the words."
    )
    assert keyword_search(ARABIC_QUERY + " zzqqxv", 5)


# ---- step 3: reciprocal rank fusion --------------------------------------------------------


def test_reciprocal_rank_fusion_adds_the_scores_of_each_list():
    from assistant.retrieval import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d", "a"]])
    assert [item for item, _ in fused] == ["b", "a", "d", "c"]
    scores = dict(fused)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61), (
        "The score of an id is the sum of 1 / (k + rank) over the lists, with k = 60, and the "
        "first id of a list has the rank 1."
    )
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 63)
    assert scores["d"] == pytest.approx(1 / 62)
    assert scores["c"] == pytest.approx(1 / 63)


def test_reciprocal_rank_fusion_accepts_lists_of_different_length():
    from assistant.retrieval import reciprocal_rank_fusion

    assert reciprocal_rank_fusion([[], []]) == []
    fused = reciprocal_rank_fusion([["a", "b"], []])
    assert [item for item, _ in fused] == ["a", "b"]
    fused = reciprocal_rank_fusion([["a"], ["b", "c", "a"], ["c"]])
    assert [item for item, _ in fused][0] == "c"  # 1/62 + 1/61 is more than 1/61 + 1/63


# ---- step 3: the modes of retrieve() ---------------------------------------------------------


def test_retrieve_rejects_an_unknown_mode(chunks):
    from assistant.retrieval import retrieve

    with pytest.raises(ValueError):
        retrieve(ENGLISH_QUERY, "magic", 5)


def test_the_vector_mode_is_the_vector_search(chunks, services):
    from assistant.retrieval import retrieve, vector_search

    assert [r["chunk_id"] for r in retrieve(ENGLISH_QUERY, "vector", 5)] == [
        r["chunk_id"] for r in vector_search(ENGLISH_QUERY, 5)
    ]


@pytest.mark.parametrize("query", [ENGLISH_QUERY, ARABIC_QUERY])
def test_the_hybrid_mode_merges_the_top_20_of_each_search(query, chunks, services):
    from assistant.retrieval import keyword_search, reciprocal_rank_fusion, retrieve, vector_search

    by_vector = [result["chunk_id"] for result in vector_search(query, 20)]
    by_keyword = [result["chunk_id"] for result in keyword_search(query, 20)]
    assert by_keyword, "The keyword search finds nothing for this question."
    fused = reciprocal_rank_fusion([by_vector, by_keyword])
    results = retrieve(query, "hybrid", 5)

    assert len(results) == 5
    assert RESULT_KEYS <= set(results[0])
    scores = dict(fused)
    returned = [result["chunk_id"] for result in results]
    assert set(returned) <= set(scores), "The hybrid mode returned a chunk that is in neither top 20."
    assert sorted((scores[chunk_id] for chunk_id in returned), reverse=True) == pytest.approx(
        [score for _, score in fused[:5]]
    ), (
        "The hybrid mode must return the 5 chunks with the highest fused score, from the top 20 "
        "of the vector search and the top 20 of the keyword search."
    )
    assert [scores[chunk_id] for chunk_id in returned] == sorted(
        (scores[chunk_id] for chunk_id in returned), reverse=True
    ), "The best fused result comes first."


class _Recorder(BaseHTTPRequestHandler):
    """Pass each request on to the real re-ranking service, and keep its body."""

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["content-length"]))
        self.server.bodies.append(json.loads(body))
        answer = httpx.post(self.server.target + self.path, content=body, timeout=600,
                            headers={"content-type": "application/json"})
        self.send_response(answer.status_code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(answer.content)))
        self.end_headers()
        self.wfile.write(answer.content)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def reranker_requests(monkeypatch, services):
    """Put a recorder in front of the re-ranking service and return the list of request bodies."""
    from assistant.embeddings import reranker_url

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    server.target, server.bodies = reranker_url(), []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("RERANKER_URL", f"http://127.0.0.1:{server.server_port}")
    yield server.bodies
    server.shutdown()


def test_the_rerank_mode_reads_the_top_20_of_the_hybrid_search(chunks, reranker_requests):
    from assistant.retrieval import retrieve

    hybrid = retrieve(ARABIC_QUERY, "hybrid", 20)
    assert not reranker_requests, "Only the mode `rerank` calls the re-ranking model."
    results = retrieve(ARABIC_QUERY, "rerank", 5)

    texts = [text for body in reranker_requests for text in body["texts"]]
    assert len(texts) == len(hybrid) == 20, (
        f"The re-ranking model got {len(texts)} texts. Give it the top 20 of the hybrid search: "
        "more texts cost time, and fewer texts lose correct chunks."
    )
    assert sorted(texts) == sorted(result["text"] for result in hybrid)
    assert len(results) == 5 and RESULT_KEYS <= set(results[0])
    assert {result["chunk_id"] for result in results} <= {result["chunk_id"] for result in hybrid}
    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True), "Order the results by the score of rerank()."

    from assistant.embeddings import rerank
    from assistant.ingest import normalise_arabic

    fresh = dict(zip(texts, rerank(normalise_arabic(ARABIC_QUERY), texts)))
    best = sorted(fresh.values(), reverse=True)[:5]
    assert sorted((fresh[result["text"]] for result in results), reverse=True) == pytest.approx(best, abs=1e-3), (
        "The mode `rerank` must return the 5 chunks to which the re-ranking model gives the "
        "highest scores."
    )


# ---- step 4: the recall table -------------------------------------------------------------


def test_the_recall_file_has_the_three_modes(capsys):
    result = read_recall_file(["vector", "hybrid", "rerank"])
    with capsys.disabled():
        print("\n  recall in the top 5       ar     en    all")
        for mode in ("vector", "hybrid", "rerank"):
            values = result["recall"][mode]
            print(f"  {mode:22} {values['ar']:5.2f}  {values['en']:5.2f}  {values['all']:5.2f}")
