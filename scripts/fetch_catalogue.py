"""Build data/catalogue.json from the KAPSARC open-data portal.

The repository already holds the result, so you do not need to run this script.
Run it only if you want a newer copy of the metadata:

    uv run python scripts/fetch_catalogue.py

Selection rule: datasets with the license "Public Domain" from Saudi publishers,
with a description, at least 3 columns and at least 10 records. The script takes
the most recently changed datasets of each theme in turn until it has 50.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

PORTAL = "https://datasource.kapsarc.org"
API = f"{PORTAL}/api/explore/v2.1/catalog/datasets"
OUT = Path(__file__).resolve().parent.parent / "data" / "catalogue.json"
TARGET = 50
PUBLISHERS = {
    "General Authority for Statistics",
    "Saudi Central Bank (SAMA)",
    "Transport General Authority",
    "Ministry of Environment, Water and Agriculture",
    "Electricity and Cogeneration Regulatory Authority",
    "King Abdullah Petroleum Studies and Research Center",
    "Saudi Open Data",
}


def plain_text(value: str | None) -> str:
    """Remove HTML tags and extra white space."""
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def fetch_page(offset: int) -> dict:
    query = urllib.parse.urlencode(
        {
            "limit": 100,
            "offset": offset,
            "order_by": "dataset_id",
            "where": 'license="Public Domain"',
        }
    )
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(f"{API}?{query}", timeout=60) as response:
                return json.load(response)
        except OSError as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"The portal did not answer for offset {offset}") from last_error


def fetch_all() -> list[dict]:
    records: list[dict] = []
    offset = 0
    while True:
        page = fetch_page(offset)
        records.extend(page["results"])
        offset += 100
        if offset >= page["total_count"]:
            return records


def select(records: list[dict]) -> list[dict]:
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        meta = record["metas"]["default"]
        if (
            meta.get("publisher") in PUBLISHERS
            and meta.get("theme")
            and len(plain_text(meta.get("description"))) >= 80
            and len(record["fields"]) >= 3
            and (meta.get("records_count") or 0) >= 10
        ):
            by_theme[meta["theme"][0]].append(record)
    for candidates in by_theme.values():
        candidates.sort(
            key=lambda r: (r["metas"]["default"]["modified"], r["dataset_id"]),
            reverse=True,
        )
    selected: list[dict] = []
    rank = 0
    while len(selected) < TARGET and any(rank < len(c) for c in by_theme.values()):
        for theme in sorted(by_theme):
            if rank < len(by_theme[theme]) and len(selected) < TARGET:
                selected.append(by_theme[theme][rank])
        rank += 1
    return sorted(selected, key=lambda r: r["dataset_id"])


def to_catalogue_entry(record: dict) -> dict:
    meta = record["metas"]["default"]
    return {
        "id": record["dataset_id"],
        "title": plain_text(meta["title"]),
        "description": plain_text(meta["description"]),
        "owner": meta["publisher"],
        "themes": [theme.strip() for theme in meta.get("theme") or []],
        "keywords": [keyword.strip() for keyword in meta.get("keyword") or []],
        "license": meta.get("license"),
        "update_frequency": meta.get("update_frequency"),
        "updated_at": meta["modified"],
        "records_count": meta["records_count"],
        "source_url": f"{PORTAL}/explore/dataset/{record['dataset_id']}/",
        "columns": [
            {
                "name": field["name"],
                "label": field.get("label"),
                "data_type": field["type"],
                "description": plain_text(field.get("description")) or None,
            }
            for field in record["fields"]
        ],
    }


def main() -> None:
    entries = [to_catalogue_entry(record) for record in select(fetch_all())]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(entries)} datasets to {OUT}")


if __name__ == "__main__":
    main()
