"""Parse, chunk, store and embed the documents. Weeks 4 and 5.

    make ingest     parse, chunk and store each fetched document     (week 4)
    make embed      embed each chunk that has no vector yet          (week 5)

The documents are the PDF files in data/documents/ (`make documents` downloads
them). The tables `documents` and `chunks` are in db/migrations/0002_documents.sql.

The id of a chunk is text that you build: <document_id>:p<page>:c<n>. The first
page of a document is page 1, and the first chunk of each page is c1. With this
rule, the same file gives the same ids each time, and an id tells the reader
where the text comes from.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from assistant.config import ROOT
from assistant.db import connect  # noqa: F401 (you will use it)

DOCUMENT_LIST = ROOT / "data" / "documents.csv"
DOCUMENT_DIR = ROOT / "data" / "documents"

# The size of one chunk and the overlap of two neighbour chunks, in words.
# A word is what str.split() gives. Change the numbers if your tests show better ones.
CHUNK_WORDS = 150
OVERLAP_WORDS = 30


def parse_pdf(path: Path) -> list[str]:
    """Return the text of each page of a PDF file. The first item is page 1.

    Return one string for each page, also for a page without text, so that the
    position in the list is always the page number minus 1. The text of a page
    must read in the correct order: the words of a line in their order, and the
    letters of a word in their order.
    """
    raise NotImplementedError("Week 4, step 3")


def normalise_arabic(text: str) -> str:
    """Return the text in the form that you store and search.

    Remove the Arabic diacritics (the marks from U+064B to U+0652, and U+0670)
    and the tatweel (U+0640). Do not change text in other scripts. Use the same
    function on each query, so that a query and a chunk have the same form.
    """
    raise NotImplementedError("Week 4, step 4")


def chunk_text(text: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    """Split a text into chunks of at most `size` words.

    Each chunk starts with the last `overlap` words of the chunk before it. The
    words of a chunk are joined with one space. A text of `size` words or less
    gives one chunk, and a text without words gives an empty list. The last
    chunk must hold at least one word that the chunk before it does not hold.
    """
    raise NotImplementedError("Week 4, step 4")


def ingest_document(document: dict[str, str], path: Path) -> int:
    """Parse one PDF file, and store the document and its chunks. Return the number of chunks.

    `document` is one row of data/documents.csv: id, title, language, publisher,
    url, sha256, pages. Chunk each page separately, so that each chunk has one
    page number. Store the normalised text.

    When you call the function again for the same document, the tables must
    hold the same rows as after the first call, and no row two times.
    """
    raise NotImplementedError("Week 4, step 4")


def embed_chunks() -> int:
    """Embed each chunk that has no vector yet, and store the vector. Return the number of chunks.

    Use embed() from assistant/embeddings.py, with some hundred chunks or less
    in each call, and commit after each call. Then you can stop the command and
    start it again without loss of the work that is done.
    """
    raise NotImplementedError("Week 5, step 2")


# ---- the command: this part is complete -----------------------------------------


def fetched_documents() -> list[tuple[dict[str, str], Path]]:
    """Return each row of data/documents.csv whose PDF file is in data/documents/."""
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
