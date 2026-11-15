"""Week 5 checks: the vectors in pgvector, the vector search, the 50 retrieval
questions and the recall of the vector search.

Run them with `make check WEEK=5`. They are free, but they are not offline in the
full sense: Postgres and the embedding service must run on your machine
(`make up`), and the chunks must have their vectors (`make embed`). The last
check reads the file that `make recall` writes.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
QUESTIONS = REPO / "evals" / "retrieval_questions.jsonl"
RECALL_FILE = REPO / "evals" / "results" / "recall.json"
RESULT_KEYS = {"chunk_id", "document_id", "title", "language", "page", "text", "score"}
ARABIC = re.compile("[\u0621-\u064a]")  # the Arabic letters
ARABIC_QUERY = "ما هي مصادر بيانات إحصاءات النقل البري؟"
# The same query with a tatweel in three words and with diacritics on two words.
ARABIC_QUERY_WITH_MARKS = "ما هي مصـــادر بيـــانات إِحْصَاءَات النَّقْل البـــري؟"


def vector_column(sql) -> str:
    """The name of the column of the table chunks that has the type vector(1024)."""
    columns = sql(
        "SELECT attname, format_type(atttypid, atttypmod) AS type FROM pg_attribute "
        "WHERE attrelid = 'chunks'::regclass AND attnum > 0 AND NOT attisdropped"
    )
    vectors = [column for column in columns if column["type"].startswith("vector")]
    assert vectors, (
        "The table chunks has no vector column. Write a migration file in db/migrations/ that "
        "creates the extension `vector` and adds a column of the type vector(1024), then run `make up`."
    )
    assert vectors[0]["type"] == "vector(1024)", (
        f"The column {vectors[0]['attname']} has the type {vectors[0]['type']}. BGE-M3 gives "
        "vectors of 1024 numbers, so the type must be vector(1024)."
    )
    return vectors[0]["attname"]


def hnsw_index(sql, column: str) -> dict:
    indexes = sql("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks'")
    found = [
        index for index in indexes
        if "using hnsw" in index["indexdef"].lower() and column in index["indexdef"]
    ]
    assert found, f"The column {column} has no HNSW index. Add one in your migration file."
    return found[0]


def sample_chunks(sql, language: str, count: int) -> list[dict]:
    """Some chunks of one language with 60 words or more, each from a different document."""
    return sql(
        "SELECT * FROM (SELECT DISTINCT ON (document_id) id, document_id, text FROM chunks "
        "WHERE language = %s AND array_length(regexp_split_to_array(btrim(text), '\\s+'), 1) >= 60 "
        "ORDER BY document_id, md5(id)) one ORDER BY md5(id) LIMIT %s",
        (language, count),
    )


def excerpt(text: str, first: int, last: int) -> str:
    return " ".join(text.split()[first:last])


# ---- step 2: the vectors and the index ------------------------------------------------


def test_the_chunks_have_a_vector_column_with_an_hnsw_index(chunks, sql):
    hnsw_index(sql, vector_column(sql))


def test_each_chunk_has_a_vector(chunks, sql):
    column = vector_column(sql)
    missing = sql(f'SELECT count(*) AS n FROM chunks WHERE "{column}" IS NULL')[0]["n"]
    assert missing == 0, f"{missing} of {chunks} chunks have no vector. Run `make embed`."


def test_each_vector_belongs_to_its_chunk(chunks, sql, services):
    from assistant.embeddings import embed

    column = vector_column(sql)
    sample = sample_chunks(sql, "en", 3) + sample_chunks(sql, "ar", 3)
    stored = {
        row["id"]: json.loads(row["vector"])
        for row in sql(
            f'SELECT id, "{column}"::text AS vector FROM chunks WHERE id = ANY(%s)',
            ([chunk["id"] for chunk in sample],),
        )
    }
    assert all(len(vector) == 1024 for vector in stored.values())
    for chunk, fresh in zip(sample, embed([chunk["text"] for chunk in sample])):
        nearest = max(stored, key=lambda chunk_id: sum(a * b for a, b in zip(fresh, stored[chunk_id])))
        assert nearest == chunk["id"], (
            f"The vector that is stored for {nearest} is the vector of the text of {chunk['id']}. "
            "Check the order of the texts and the vectors in each batch of embed_chunks()."
        )


# ---- step 2: the vector search ---------------------------------------------------------


def test_vector_search_returns_the_best_chunks_first(chunks, sql, services):
    from assistant.retrieval import vector_search

    results = vector_search("How is the sample of the survey selected?", 5)
    assert len(results) == 5, "vector_search(query, 5) returns 5 results."
    for result in results:
        assert RESULT_KEYS <= set(result), f"A result needs the keys {sorted(RESULT_KEYS - set(result))}."
    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True), "The best result comes first, with the highest score."
    ids = [result["chunk_id"] for result in results]
    rows = {row["id"]: row for row in sql("SELECT id, page, document_id FROM chunks WHERE id = ANY(%s)", (ids,))}
    assert len(rows) == 5, "Each chunk_id must be the id of a row of the table chunks, one time."
    for result in results:
        assert (result["page"], result["document_id"]) == (
            rows[result["chunk_id"]]["page"],
            rows[result["chunk_id"]]["document_id"],
        )
    assert len(vector_search("How is the sample of the survey selected?", 3)) == 3


@pytest.mark.parametrize("language", ["en", "ar"])
def test_vector_search_finds_a_chunk_from_a_part_of_its_text(language, chunks, sql, services):
    from assistant.retrieval import vector_search

    for chunk in sample_chunks(sql, language, 2):
        query = excerpt(chunk["text"], 5, 55)
        found = [result for result in vector_search(query, 5) if query in result["text"]]
        assert found, (
            f"A search with 50 words of the chunk {chunk['id']} does not return this chunk in "
            "the top 5. Check that you embed the query with embed(), and that the distance "
            "operator of the query fits the vectors."
        )


def test_vector_search_normalises_the_query(chunks, services):
    from assistant.retrieval import vector_search

    plain = [result["chunk_id"] for result in vector_search(ARABIC_QUERY, 5)]
    marked = [result["chunk_id"] for result in vector_search(ARABIC_QUERY_WITH_MARKS, 5)]
    assert marked == plain, (
        "The same Arabic query with diacritics and tatweel gives other results. Normalise the "
        "query with normalise_arabic() before you embed it, as you did with the chunks."
    )


def test_vector_search_uses_the_hnsw_index(chunks, sql, services, monkeypatch):
    from assistant.retrieval import vector_search

    index = hnsw_index(sql, vector_column(sql))["indexname"]

    def scans() -> int:
        row = sql("SELECT idx_scan FROM pg_stat_user_indexes WHERE indexrelname = %s", (index,))
        return row[0]["idx_scan"] or 0

    # The table has only some thousands of rows, so the planner can find a full read of the
    # table cheaper than the index. This setting of the connections that vector_search() opens
    # makes the full read the last choice. The index is used only when the query can use it.
    monkeypatch.setenv("PGOPTIONS", "-c enable_seqscan=off")
    before = scans()
    vector_search("Which administrative records does the publication use?", 5)
    deadline = time.monotonic() + 5  # Postgres reports the scan a moment after the query.
    while scans() == before and time.monotonic() < deadline:
        time.sleep(0.2)
    assert scans() > before, (
        f"The search did not use the index {index}. An index helps only a query that orders by "
        "the distance operator of the index, for example `<=>` for vector_cosine_ops, with a "
        "LIMIT. In psql, run `SET enable_seqscan = off;`, then run your query with EXPLAIN and read the plan."
    )


# ---- step 3: the retrieval questions ------------------------------------------------------


def load_questions() -> list[dict]:
    assert QUESTIONS.exists(), "evals/retrieval_questions.jsonl does not exist. Run `make start PHASE=2`."
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_there_are_50_retrieval_questions_in_two_languages(chunks, sql):
    questions = load_questions()
    assert len(questions) == 50, f"evals/retrieval_questions.jsonl has {len(questions)} questions, not 50."
    assert len({question["id"] for question in questions}) == 50, "Each question needs its own id."
    assert len({question["question"].strip() for question in questions}) == 50, "Two questions have the same text."
    by_language = {"ar": 0, "en": 0}
    for question in questions:
        assert question["language"] in by_language, f"{question['id']}: the language is \"ar\" or \"en\"."
        by_language[question["language"]] += 1
        is_arabic = bool(ARABIC.search(question["question"]))
        assert is_arabic == (question["language"] == "ar"), (
            f"{question['id']}: the language of the question text is not {question['language']}."
        )
        assert question["expected_chunk_ids"], f"{question['id']}: write at least one expected chunk id."
    assert by_language == {"ar": 25, "en": 25}, f"Write 25 questions in each language. Now: {by_language}"
    expected = sorted({chunk_id for question in questions for chunk_id in question["expected_chunk_ids"]})
    known = {row["id"] for row in sql("SELECT id FROM chunks WHERE id = ANY(%s)", (expected,))}
    unknown = [chunk_id for chunk_id in expected if chunk_id not in known]
    assert not unknown, (
        f"{len(unknown)} expected chunk ids are not in the table chunks, for example {unknown[:3]}. "
        "If you changed the chunk size after you wrote the questions, the ids changed too."
    )


# ---- step 4: the recall ---------------------------------------------------------------------

FAKE_QUESTIONS = [
    {"id": "t1", "language": "en", "question": "first", "expected_chunk_ids": ["doc-a:p1:c1"]},
    {"id": "t2", "language": "en", "question": "second", "expected_chunk_ids": ["doc-b:p2:c1", "doc-b:p2:c2"]},
    {"id": "t3", "language": "ar", "question": "third", "expected_chunk_ids": ["doc-c:p3:c1"]},
    {"id": "t4", "language": "ar", "question": "fourth", "expected_chunk_ids": ["doc-d:p4:c1"]},
]
OTHER = [f"other:p1:c{number}" for number in range(1, 10)]
# What the fake search returns, for each mode and each question.
FAKE_RESULTS = {
    "vector": {
        "first": OTHER[:4] + ["doc-a:p1:c1"],  # found at rank 5
        "second": ["doc-b:p2:c2"] + OTHER,  # one of the two expected chunks is enough
        "third": OTHER,  # not found
        "fourth": OTHER[:5] + ["doc-d:p4:c1"],  # at rank 6: not found in the top 5
    },
    "hybrid": {
        "first": ["doc-a:p1:c1"] + OTHER,
        "second": OTHER,
        "third": ["doc-c:p3:c1"] + OTHER,
        "fourth": ["doc-d:p4:c1"] + OTHER,
    },
}


@pytest.fixture
def fake_retrieve(monkeypatch):
    """Replace retrieve() with a function that returns the lists above."""
    import assistant.retrieval
    import evals.recall

    calls = []

    def retrieve(*args, **kwargs):
        names = ("query_text", "mode", "k")
        given = dict(zip(names, args), **kwargs)
        query = given.get("query_text", given.get("query"))
        mode, k = given.get("mode", "rerank"), given.get("k", 5)
        calls.append((query, mode, k))
        return [{"chunk_id": chunk_id} for chunk_id in FAKE_RESULTS[mode][query][:k]]

    monkeypatch.setattr(assistant.retrieval, "retrieve", retrieve)
    if hasattr(evals.recall, "retrieve"):
        monkeypatch.setattr(evals.recall, "retrieve", retrieve)
    return calls


def test_measure_computes_the_recall_for_each_mode_and_each_language(fake_retrieve):
    from evals.recall import measure

    result = measure(FAKE_QUESTIONS, ["vector", "hybrid"], 5)

    assert result["k"] == 5 and result["questions"] == 4
    assert result["recall"]["vector"] == pytest.approx({"ar": 0.0, "en": 1.0, "all": 0.5}), (
        "A question is found when at least one expected chunk id is in the top k results. The "
        "recall is the number of found questions divided by the number of questions."
    )
    assert result["recall"]["hybrid"] == pytest.approx({"ar": 1.0, "en": 0.5, "all": 0.75})
    rows = {(row["id"], row["mode"]): row for row in result["rows"]}
    assert len(rows) == len(result["rows"]) == 8, "`rows` has one item for each question and each mode."
    assert rows[("t1", "vector")]["found"] is True
    assert rows[("t4", "vector")]["found"] is False
    assert rows[("t4", "vector")]["retrieved_chunk_ids"] == OTHER[:5]
    assert rows[("t2", "hybrid")]["expected_chunk_ids"] == ["doc-b:p2:c1", "doc-b:p2:c2"]
    assert {call[2] for call in fake_retrieve} == {5}, "Pass k to retrieve()."


def test_measure_uses_k(fake_retrieve):
    from evals.recall import measure

    result = measure(FAKE_QUESTIONS, ["vector"], 6)
    assert result["recall"]["vector"] == pytest.approx({"ar": 0.5, "en": 1.0, "all": 0.75})


def read_recall_file(modes: list[str]) -> dict:
    """Read evals/results/recall.json and check that it agrees with itself and with your questions."""
    assert RECALL_FILE.exists(), (
        f"{RECALL_FILE.relative_to(REPO)} does not exist. Run `make recall ARGS=\"--modes {','.join(modes)}\"`."
    )
    result = json.loads(RECALL_FILE.read_text(encoding="utf-8"))
    questions = {question["id"]: question for question in load_questions()}
    assert result["k"] == 5, "Measure the recall in the top five results (k = 5)."
    for mode in modes:
        assert mode in result["recall"], (
            f"The file has no recall for the mode `{mode}`. Run `make recall` with this mode."
        )
        rows = [row for row in result["rows"] if row["mode"] == mode]
        assert {row["id"] for row in rows} == set(questions), (
            f"The rows of the mode `{mode}` are not the questions of evals/retrieval_questions.jsonl. "
            "Run `make recall` again after each change of the questions."
        )
        for row in rows:
            question = questions[row["id"]]
            assert row["expected_chunk_ids"] == question["expected_chunk_ids"], (
                f"{row['id']}: the expected chunk ids changed after the run. Run `make recall` again."
            )
            assert len(row["retrieved_chunk_ids"]) <= 5
            assert row["found"] is bool(set(row["expected_chunk_ids"]) & set(row["retrieved_chunk_ids"]))
        for language in ("ar", "en", "all"):
            group = [row for row in rows if language in (row["language"], "all")]
            assert len(group) == (50 if language == "all" else 25)
            assert result["recall"][mode][language] == pytest.approx(
                sum(row["found"] for row in group) / len(group)
            ), f"The recall of `{mode}` for `{language}` does not agree with the rows of the file."
    return result


def test_the_recall_file_has_the_recall_of_the_vector_search(capsys):
    result = read_recall_file(["vector"])
    with capsys.disabled():
        values = result["recall"]["vector"]
        print(f"\n  recall in the top 5, vector search: ar {values['ar']:.2f}, en {values['en']:.2f}")
