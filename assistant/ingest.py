"""Reference solution."""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path

import pymupdf

from assistant.config import ROOT
from assistant.db import connect
from assistant.embeddings import embed

DOCUMENT_LIST = ROOT / "data" / "documents.csv"
DOCUMENT_DIR = ROOT / "data" / "documents"
CHUNK_WORDS = 150
OVERLAP_WORDS = 30
EMBED_BATCH = 64

DIACRITICS = re.compile("[\u064b-\u0652\u0670\u0640]")
PRESENTATION_FORMS = re.compile("[\ufb50-\ufdff\ufe70-\ufefc]+")
DOT_LEADERS = re.compile(r"(\.\s?){4,}")


def _line_text(line: dict) -> str:
    """The text of one line. PyMuPDF gives the characters of a ligature in reverse order.

    The font has one glyph for a pair such as lam + alef. PyMuPDF returns the
    characters of the pair as alef, then lam. All characters of the glyph except
    the last one have a box of width 0, so the group is easy to find.
    """
    fixed: list[str] = []
    group: list[str] = []
    for span in line["spans"]:
        for char in span["chars"]:
            x0, _, x1, _ = char["bbox"]
            group.append(char["c"])
            if abs(x1 - x0) > 0.01:
                fixed.extend(reversed(group))
                group = []
    fixed.extend(group)
    return "".join(fixed)


def parse_pdf(path: Path) -> list[str]:
    pages = []
    with pymupdf.open(path) as document:
        for page in document:
            lines = []
            for block in page.get_text("rawdict")["blocks"]:
                for line in block.get("lines", []):
                    lines.append(_line_text(line))
            pages.append(DOT_LEADERS.sub(" ", "\n".join(lines)))
    return pages


def normalise_arabic(text: str) -> str:
    text = PRESENTATION_FORMS.sub(lambda match: unicodedata.normalize("NFKC", match.group()), text)
    return DIACRITICS.sub("", text)


def chunk_text(text: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = size - overlap
    chunks = []
    start = 0
    while True:
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
        start += step
    return chunks


def ingest_document(document: dict[str, str], path: Path) -> int:
    pages = parse_pdf(path)
    rows = []
    for page_number, page_text in enumerate(pages, start=1):
        for position, chunk in enumerate(chunk_text(normalise_arabic(page_text)), start=1):
            chunk_id = f"{document['id']}:p{page_number}:c{position}"
            rows.append((chunk_id, document["id"], document["language"], page_number, position, chunk))
    with connect() as connection:
        connection.execute(
            "INSERT INTO documents (id, title, language, publisher, url, pages) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, language = EXCLUDED.language, "
            "publisher = EXCLUDED.publisher, url = EXCLUDED.url, pages = EXCLUDED.pages",
            (document["id"], document["title"], document["language"], document["publisher"],
             document["url"], len(pages)),
        )
        # Keep each chunk whose text is the same, so that its vector stays valid.
        stored = {
            row["id"]: row["text"]
            for row in connection.execute(
                "SELECT id, text FROM chunks WHERE document_id = %s", (document["id"],)
            )
        }
        new = {row[0]: row[5] for row in rows}
        stale = [chunk_id for chunk_id, text in stored.items() if new.get(chunk_id) != text]
        if stale:
            connection.execute("DELETE FROM chunks WHERE id = ANY(%s)", (stale,))
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO chunks (id, document_id, language, page, position, text) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                rows,
            )
    return len(rows)


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7g}" for value in vector) + "]"


def embed_chunks() -> int:
    done = 0
    with connect() as connection:
        while True:
            rows = connection.execute(
                "SELECT id, text FROM chunks WHERE embedding IS NULL ORDER BY id LIMIT %s",
                (EMBED_BATCH,),
            ).fetchall()
            if not rows:
                return done
            vectors = embed([row["text"] for row in rows])
            with connection.cursor() as cursor:
                cursor.executemany(
                    "UPDATE chunks SET embedding = %s::vector WHERE id = %s",
                    [(vector_literal(vector), row["id"]) for row, vector in zip(rows, vectors)],
                )
            connection.commit()
            done += len(rows)
            print(f"  embedded {done} chunks", flush=True)


def fetched_documents() -> list[tuple[dict[str, str], Path]]:
    with DOCUMENT_LIST.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    found = [(row, DOCUMENT_DIR / f"{row['id']}.pdf") for row in rows]
    return [(row, path) for row, path in found if path.exists()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the documents of data/documents/.")
    parser.add_argument("--embed", action="store_true", help="embed the chunks that have no vector")
    args = parser.parse_args()
    if args.embed:
        print(f"Embedded {embed_chunks()} chunks.")
        return
    documents = fetched_documents()
    if not documents:
        raise SystemExit("data/documents/ has no PDF files. Run `make documents` first.")
    total = 0
    for number, (document, path) in enumerate(documents, start=1):
        count = ingest_document(document, path)
        total += count
        print(f"{number:3}/{len(documents)}  {document['id']}  {count} chunks")
    print(f"Stored {total} chunks of {len(documents)} documents.")


if __name__ == "__main__":
    main()
