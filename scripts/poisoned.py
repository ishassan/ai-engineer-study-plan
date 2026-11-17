"""Load the poisoned documents and datasets of the attack suite, or remove them. Phase 5, week 18.

    make poison      load data/poisoned/ into the tables documents, chunks and datasets
    make unpoison    remove them again

Each row that this script writes has an id that starts with `poisoned-`. That prefix is the
marker: `make unpoison` deletes each document and each dataset with it, and nothing else.

The folder data/poisoned/ holds your attack material:

- One Markdown file for each poisoned document, for example `water-note-en.md`. The first
  lines are the header, then an empty line, then the text:

      title: Water use notes 2024
      language: en

      The text of the document. Put the hidden instruction somewhere in the text.

  The language is `en` or `ar`. A line that holds only `---page---` starts a new page. The
  document gets the id `poisoned-<file name without .md>`. The script chunks the text with
  chunk_text() and normalise_arabic() of your assistant/ingest.py, and embeds the new chunks
  with embed_chunks(), as `make ingest` and `make embed` do.
- Optional: `datasets.jsonl`, one poisoned catalogue entry on each line, with the keys `id`
  (it must start with `poisoned-`), `title`, `description`, `owner`, and optionally `themes`
  and `keywords` (lists of strings). search_datasets then finds these entries, so their text
  reaches the model as a tool result.

You can run `make poison` again after a change: it removes the old rows first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # `python scripts/poisoned.py` must find the package assistant.

from assistant.db import connect  # noqa: E402

FOLDER = ROOT / "data" / "poisoned"
PREFIX = "poisoned-"
PUBLISHER = "Attack suite (poisoned)"
PAGE_BREAK = "---page---"


def read_document(path: Path) -> tuple[dict[str, str], list[str]]:
    """The header fields and the pages of one Markdown file."""
    header_text, _, body = path.read_text(encoding="utf-8").partition("\n\n")
    header = {}
    for line in header_text.splitlines():
        key, _, value = line.partition(":")
        header[key.strip().lower()] = value.strip()
    if header.get("language") not in {"en", "ar"} or not header.get("title"):
        raise SystemExit(f"{path.name}: the header needs `title:` and `language: en` (or ar), then an empty line.")
    pages = [page.strip() for page in body.split(f"\n{PAGE_BREAK}\n")]
    return header, [page for page in pages if page]


def remove() -> tuple[int, int]:
    with connect() as connection:
        documents = connection.execute("DELETE FROM documents WHERE id LIKE %s", (PREFIX + "%",)).rowcount
        datasets = connection.execute("DELETE FROM datasets WHERE id LIKE %s", (PREFIX + "%",)).rowcount
    return documents, datasets


def load() -> None:
    from assistant.ingest import chunk_text, embed_chunks, normalise_arabic

    remove()
    files = sorted(FOLDER.glob("*.md")) if FOLDER.is_dir() else []
    files = [path for path in files if path.name.lower() != "readme.md"]
    chunks = 0
    with connect() as connection:
        for path in files:
            header, pages = read_document(path)
            document_id = PREFIX + path.stem
            connection.execute(
                "INSERT INTO documents (id, title, language, publisher, url, pages) VALUES (%s, %s, %s, %s, %s, %s)",
                (document_id, header["title"], header["language"], PUBLISHER,
                 f"data/poisoned/{path.name}", len(pages)),
            )
            for page_number, page in enumerate(pages, start=1):
                for position, text in enumerate(chunk_text(normalise_arabic(page)), start=1):
                    connection.execute(
                        "INSERT INTO chunks (id, document_id, language, page, position, text) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (f"{document_id}:p{page_number}:c{position}", document_id, header["language"],
                         page_number, position, text),
                    )
                    chunks += 1
        datasets_file = FOLDER / "datasets.jsonl"
        lines = datasets_file.read_text(encoding="utf-8").splitlines() if datasets_file.exists() else []
        datasets = [json.loads(line) for line in lines if line.strip()]
        for dataset in datasets:
            if not str(dataset.get("id", "")).startswith(PREFIX):
                raise SystemExit(f"datasets.jsonl: each id must start with {PREFIX!r}: {dataset.get('id')!r}")
            connection.execute(
                "INSERT INTO datasets (id, title, description, owner, themes, keywords, license, "
                "update_frequency, updated_at, records_count, source_url) "
                "VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, now(), 0, '')",
                (dataset["id"], dataset["title"], dataset["description"], dataset["owner"],
                 dataset.get("themes", []), dataset.get("keywords", [])),
            )
    embedded = embed_chunks()
    print(f"Loaded {len(files)} poisoned documents ({chunks} chunks, {embedded} embedded) "
          f"and {len(datasets)} poisoned datasets.")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "load":
        load()
    elif command == "remove":
        documents, datasets = remove()
        print(f"Removed {documents} poisoned documents and {datasets} poisoned datasets.")
    else:
        sys.exit("Usage: python scripts/poisoned.py load|remove")


if __name__ == "__main__":
    main()
