"""Download the documents of Phase 2 into data/documents/.

    make documents

data/documents.csv lists 100 public PDF files of the General Authority for
Statistics: 50 in English and 50 in Arabic. Most are the methodology and quality
report of one statistical product. The repository holds only the list. This
script downloads each file to data/documents/<id>.pdf and compares its SHA-256
hash with the hash in the list.

You can run the script again at any time. It keeps each file that is complete,
and it downloads only the files that are missing or wrong. A publisher can
replace or remove a file. Then the script reports the file and continues, and
the lab works with the files that you have.
"""

from __future__ import annotations

import csv
import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "data" / "documents.csv"
OUT = ROOT / "data" / "documents"
# Some sites refuse a request that has no browser-like User-Agent header.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; document-fetcher)", "Accept": "application/pdf,*/*"}
PAUSE_SECONDS = 1.0
ATTEMPTS = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{type(last_error).__name__}: {last_error}")


def main() -> None:
    with LIST.open(newline="", encoding="utf-8") as file:
        documents = list(csv.DictReader(file))
    OUT.mkdir(parents=True, exist_ok=True)
    kept, fetched, failed = 0, 0, []
    for number, document in enumerate(documents, start=1):
        target = OUT / f"{document['id']}.pdf"
        if target.exists() and sha256(target.read_bytes()) == document["sha256"]:
            kept += 1
            continue
        try:
            data = download(document["url"])
        except RuntimeError as error:
            failed.append((document["id"], f"download failed: {error}"))
            continue
        finally:
            time.sleep(PAUSE_SECONDS)  # Be polite to the server of the publisher.
        if sha256(data) != document["sha256"]:
            failed.append((document["id"], "the file on the server is not the file in the list"))
            continue
        target.write_bytes(data)
        fetched += 1
        print(f"{number:3}/{len(documents)}  {document['id']}  {len(data) / 1e6:.1f} MB")
    print(f"\n{kept + fetched} of {len(documents)} documents are in {OUT.relative_to(ROOT)}/.")
    if failed:
        print(f"{len(failed)} documents failed:")
        for document_id, reason in failed:
            print(f"  {document_id}: {reason}")
        sys.exit(1)


if __name__ == "__main__":
    main()
