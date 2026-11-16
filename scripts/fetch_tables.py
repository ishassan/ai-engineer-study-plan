"""Download the records of some catalogue datasets from the KAPSARC open-data portal. Phase 4.

The repository already holds the result in data/tables/, so you do not need to run this
script. Run it only if you want a newer copy of the records:

    uv run python scripts/fetch_tables.py

For each dataset in TABLES, the script writes data/tables/<table>.csv (the CSV export of the
portal) and adds one entry to data/tables/sources.json: the table, the dataset ID, the title,
the publisher, the license, the URL of the export, the time of the download, and the name and
type of each column. scripts/load_tables.py reads these files.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PORTAL = "https://datasource.kapsarc.org"
API = f"{PORTAL}/api/explore/v2.1/catalog/datasets"
OUT = Path(__file__).resolve().parent.parent / "data" / "tables"

# The name of the table in the schema `data`, and the ID of the dataset in data/catalogue.json.
TABLES = {
    "cement": "cement-production-and-sales",
    "crude_oil_production": "saudi-crude-oil-production-from-sama-annual-statistics-2015-dec",
    "electricity_consumption": "electricity-consumption-by-sectors",
    "gas_sales": "gas-sales-by-region-2001-2013",
    "generation_capacity": "installed-generation-capacity-peak-load-in-mw-by-region-for-2014",
    "population": "population-by-gender-age-nationality-saudinon-saudi",
    "water_use_per_capita": "per_capita_average_water_use_in_saudi_regions",
    "world_oil_production": "world-oil-production",
}


def fetch(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except OSError as error:
            last_error = error
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"The portal did not answer: {url}") from last_error


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    for table, dataset_id in TABLES.items():
        meta = json.loads(fetch(f"{API}/{dataset_id}"))
        default = meta["metas"]["default"]
        if default.get("license") != "Public Domain":
            raise SystemExit(f"{dataset_id} has the license {default.get('license')!r}, not Public Domain.")
        export = f"{API}/{dataset_id}/exports/csv?delimiter=%2C"
        text = fetch(export).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        header, records = rows[0], rows[1:]
        types = {field["name"]: field["type"] for field in meta["fields"]}
        with open(OUT / f"{table}.csv", "w", newline="", encoding="utf-8") as file:
            csv.writer(file, lineterminator="\n").writerows([header, *records])
        sources.append({
            "table": table,
            "dataset_id": dataset_id,
            "title": default.get("title"),
            "publisher": default.get("publisher"),
            "license": default["license"],
            "source_url": export,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "records": len(records),
            "columns": [{"name": name, "type": types.get(name, "text")} for name in header],
        })
        print(f"{table}: {len(records)} records")
    (OUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
