"""Week 4 checks: parse the documents, normalise the Arabic text, chunk and store.

Run them with `make check WEEK=4`. They are free. Postgres must run (`make up`),
and the documents must be in data/documents/ (`make documents`). The last four
checks read the tables after `make ingest`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
DOCUMENT_DIR = REPO / "data" / "documents"
CHUNK_ID = re.compile(r"^(?P<document>.+):p(?P<page>[1-9]\d*):c(?P<n>[1-9]\d*)$")
# The Arabic diacritics and the tatweel, as a Postgres regular expression.
MARKS = "[\u064b-\u0652\u0670\u0640]"
CHECK_DOCUMENT = "lab-check-document"


def squash(text: str) -> str:
    """Remove the diacritics and the tatweel, and make each run of white space one space."""
    return re.sub(r"\s+", " ", re.sub(MARKS, "", text))


def pdf(document_id: str) -> Path:
    path = DOCUMENT_DIR / f"{document_id}.pdf"
    if not path.exists():
        pytest.fail(f"{path.relative_to(REPO)} does not exist. Run `make documents`.", pytrace=False)
    return path


# ---- step 3: parse ----------------------------------------------------------------


def test_parse_pdf_returns_the_text_of_each_page():
    from assistant.ingest import parse_pdf

    pages = parse_pdf(pdf("gastat-land-transport-en"))
    assert isinstance(pages, list) and all(isinstance(page, str) for page in pages)
    assert len(pages) == 24, "Return one string for each page of the PDF, in the order of the pages."
    assert (
        "An open transportation route for the use of motorized vehicles, excluding railways"
        in squash(pages[6])
    ), "This sentence is on page 7 of the document, so it must be in the seventh string."


def test_the_arabic_words_are_in_the_correct_order():
    from assistant.ingest import parse_pdf

    pages = parse_pdf(pdf("gastat-national-accounts-ar"))
    assert len(pages) == 29
    assert (
        "قطاع يتكون من جميع الشركات المقيمة التي تعمل بصورة رئيسية في توفير الخدمات المالية"
        in squash(pages[6])
    ), (
        "Page 7 of gastat-national-accounts-ar.pdf holds this sentence. In your text the words "
        "are in a different order. Open the PDF, and compare the page with your text."
    )


def test_the_letters_of_arabic_ligatures_are_in_the_correct_order():
    from assistant.ingest import parse_pdf

    page = squash(parse_pdf(pdf("gastat-national-accounts-ar"))[6])
    assert "خدمات البنوك وصناديق الاستثمار وخدمات التأمين وتمويل المعاشات التقاعدية" in page, (
        "Page 7 of gastat-national-accounts-ar.pdf holds the word الاستثمار. A parser that reads "
        "the glyph for lam + alef in the wrong order gives االستثمار. Look for this error in "
        "your text, and correct the parser or use a different one."
    )
    page = squash(parse_pdf(pdf("gastat-census-2022-ar"))[9])
    assert "يضمن تحديث جميع المعلومات السكانية الضرورية باستمرار" in page, (
        "Page 10 of gastat-census-2022-ar.pdf holds the words تحديث and المعلومات. This file has "
        "more ligatures than lam + alef, and each one must come out in the correct order."
    )


# ---- step 4: normalise and chunk -----------------------------------------------------


def test_normalise_arabic_removes_diacritics_and_tatweel():
    from assistant.ingest import normalise_arabic

    assert normalise_arabic("مُحَمَّدٌ") == "محمد", "Remove the diacritics U+064B to U+0652."
    assert normalise_arabic("الجـــدول") == "الجدول", "Remove the tatweel U+0640."
    assert normalise_arabic("رَحْمٰن") == "رحمن", "Remove the superscript alef U+0670."
    assert normalise_arabic("كِتَابُ الْبَيَانَاتِ، 2024") == "كتاب البيانات، 2024"


def test_normalise_arabic_keeps_other_text():
    from assistant.ingest import normalise_arabic

    text = "Table 3: Road length (km), 2019-2024. Source: GASTAT."
    assert normalise_arabic(text) == text
    assert normalise_arabic("جدول البيانات") == "جدول البيانات"


def test_chunk_text_makes_chunks_of_a_fixed_size_with_overlap():
    from assistant.ingest import chunk_text

    words = [f"w{number}" for number in range(100)]
    chunks = chunk_text(" ".join(words), size=30, overlap=10)

    assert [chunk.split() for chunk in chunks[:2]] == [words[0:30], words[20:50]], (
        "With size=30 and overlap=10, the first chunk is words 0 to 29 and the second chunk is "
        "words 20 to 49: it starts with the last 10 words of the first chunk."
    )
    assert all(len(chunk.split()) <= 30 for chunk in chunks)
    assert chunks[-1].split()[-1] == "w99", "The last chunk must end with the last word of the text."
    for before, after in zip(chunks, chunks[1:]):
        assert after.split()[:10] == before.split()[-10:], "Each chunk starts with the overlap."
    assert len(chunks) == 5, (
        f"100 words with size=30 and overlap=10 give 5 chunks, not {len(chunks)}. The last "
        "chunk must hold at least one word that the chunk before it does not hold."
    )


def test_chunk_text_handles_short_and_empty_text():
    from assistant.ingest import chunk_text

    assert chunk_text("one two  three\nfour", size=30, overlap=10) == ["one two three four"]
    assert chunk_text(" ".join(["w"] * 30), size=30, overlap=10) == [" ".join(["w"] * 30)]
    assert chunk_text("", size=30, overlap=10) == []
    assert chunk_text(" \n\t ", size=30, overlap=10) == []


# ---- step 4: store -----------------------------------------------------------------


@pytest.fixture
def check_document(tmp_path, sql):
    """A PDF file with three pages: 400 words, no text, and 90 words."""
    import pymupdf

    page_words = [
        [f"alpha{number:03}" for number in range(400)],
        [],
        [f"beta{number:03}" for number in range(90)],
    ]
    path = tmp_path / f"{CHECK_DOCUMENT}.pdf"
    with pymupdf.open() as document:
        for words in page_words:
            page = document.new_page()
            lines = [" ".join(words[start : start + 8]) for start in range(0, len(words), 8)]
            page.insert_text((50, 60), "\n".join(lines), fontsize=9)
        document.save(path)
    row = {
        "id": CHECK_DOCUMENT,
        "title": "A document of the lab checks",
        "language": "en",
        "publisher": "Lab",
        "url": "https://example.com/lab-check-document.pdf",
        "sha256": "",
        "pages": "3",
    }
    sql("DELETE FROM documents WHERE id = %s", (CHECK_DOCUMENT,))
    yield row, path, page_words
    sql("DELETE FROM documents WHERE id = %s", (CHECK_DOCUMENT,))


def test_ingest_document_stores_the_chunks_of_each_page(check_document, sql):
    from assistant.ingest import ingest_document

    row, path, page_words = check_document
    count = ingest_document(row, path)
    stored = sql(
        "SELECT * FROM chunks WHERE document_id = %s ORDER BY page, position", (CHECK_DOCUMENT,)
    )

    assert sql("SELECT title, language FROM documents WHERE id = %s", (CHECK_DOCUMENT,)) == [
        {"title": row["title"], "language": "en"}
    ], "Store one row in the table documents."
    assert count == len(stored) > 0, "Return the number of chunks that the document has."
    assert {chunk["page"] for chunk in stored} == {1, 3}, (
        "Chunk each page separately. Page 2 has no text, so it has no chunk, and the chunks "
        "of the last page have the page number 3."
    )
    for chunk in stored:
        assert chunk["id"] == f"{CHECK_DOCUMENT}:p{chunk['page']}:c{chunk['position']}"
        assert chunk["language"] == "en"
    for page, words in ((1, page_words[0]), (3, page_words[2])):
        of_page = [chunk for chunk in stored if chunk["page"] == page]
        assert [chunk["position"] for chunk in of_page] == list(range(1, len(of_page) + 1)), (
            "The first chunk of each page is c1, the next one is c2."
        )
        found = [word for chunk in of_page for word in chunk["text"].split()]
        assert found[0] == words[0] and found[-1] == words[-1]
        assert set(found) == set(words), f"The chunks of page {page} do not hold each word of the page."
    assert len([chunk for chunk in stored if chunk["page"] == 1]) >= 2, (
        "Page 1 has 400 words. Split it into more than one chunk."
    )


def test_ingest_document_gives_the_same_rows_when_it_runs_again(check_document, sql):
    from assistant.ingest import ingest_document

    row, path, _ = check_document
    ingest_document(row, path)
    first = sql("SELECT id, text FROM chunks WHERE document_id = %s ORDER BY id", (CHECK_DOCUMENT,))
    count = ingest_document(row, path)
    second = sql("SELECT id, text FROM chunks WHERE document_id = %s ORDER BY id", (CHECK_DOCUMENT,))

    assert second == first, "The second run must leave the same chunks, with the same ids."
    assert count == len(second)
    assert sql("SELECT count(*) AS n FROM documents WHERE id = %s", (CHECK_DOCUMENT,))[0]["n"] == 1


def test_each_fetched_document_is_in_the_tables(documents, chunks, sql):
    stored = {row["id"]: row for row in sql("SELECT id, language, pages FROM documents")}
    with_chunks = {row["document_id"] for row in sql("SELECT DISTINCT document_id FROM chunks")}
    missing = sorted(row["id"] for row in documents if row["id"] not in with_chunks)

    assert not missing, f"{len(missing)} fetched documents have no chunks. Run `make ingest`. First: {missing[:3]}"
    for row in documents:
        assert stored[row["id"]]["language"] == row["language"]
        assert stored[row["id"]]["pages"] == int(row["pages"]), (
            f"{row['id']}: store the number of pages of the PDF in documents.pages."
        )
    languages = {row["language"] for row in sql("SELECT DISTINCT language FROM chunks")}
    assert languages == {"ar", "en"}


def test_each_chunk_has_its_id_its_page_and_its_language(chunks, sql):
    wrong = sql(
        "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE c.id <> c.document_id || ':p' || c.page || ':c' || c.position "
        "   OR c.language <> d.language OR c.page < 1 OR c.page > d.pages OR c.position < 1 LIMIT 5"
    )
    assert not wrong, (
        "The id of a chunk is <document_id>:p<page>:c<n>, the page is between 1 and the number "
        f"of pages, and the language is the language of the document. Wrong: {[r['id'] for r in wrong]}"
    )
    gaps = sql(
        "SELECT document_id, page FROM chunks GROUP BY document_id, page "
        "HAVING max(position) <> count(*) LIMIT 5"
    )
    assert not gaps, f"The chunks of a page are c1, c2, c3 with no gap. Wrong pages: {gaps}"
    assert all(CHUNK_ID.match(row["id"]) for row in sql("SELECT id FROM chunks LIMIT 200"))


def test_the_stored_text_is_normalised_and_not_too_long(chunks, sql):
    marked = sql("SELECT id FROM chunks WHERE text ~ %s LIMIT 5", (MARKS,))
    assert not marked, (
        "These chunks hold diacritics or tatweel. Store the text that normalise_arabic() "
        f"returns: {[row['id'] for row in marked]}"
    )
    assert not sql("SELECT id FROM chunks WHERE btrim(text) = '' LIMIT 1"), "A chunk has no text."
    longest = sql(
        "SELECT id, array_length(regexp_split_to_array(btrim(text), '\\s+'), 1) AS words "
        "FROM chunks ORDER BY 2 DESC LIMIT 1"
    )[0]
    assert longest["words"] <= 600, (
        f"{longest['id']} has {longest['words']} words. The model services cut each text at 2048 "
        "tokens, and an Arabic word has more than 2 tokens on average. Keep each chunk below 600 words."
    )
