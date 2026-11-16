"""Load data/tables/*.csv into the tables of the schema `data`. Phase 4, week 16.

The migration db/migrations/0007_data_tables.sql makes the schema and the tables. This script
replaces the rows of each table with the rows of its CSV file, and writes data.sources from
data/tables/sources.json. You can run it again at any time. `make up` calls it. Before the
migration exists (Phases 1 to 3), the script does nothing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

TABLES = Path(__file__).resolve().parent.parent / "data" / "tables"
DEFAULT_URL = "postgresql://assistant:assistant@localhost:5432/assistant"

UPSERT_SOURCE = """
INSERT INTO data.sources (table_name, dataset_id, title, publisher, license, source_url, fetched_at, records)
VALUES (%(table)s, %(dataset_id)s, %(title)s, %(publisher)s, %(license)s, %(source_url)s, %(fetched_at)s, %(records)s)
ON CONFLICT (table_name) DO UPDATE SET
    dataset_id = EXCLUDED.dataset_id,
    title = EXCLUDED.title,
    publisher = EXCLUDED.publisher,
    license = EXCLUDED.license,
    source_url = EXCLUDED.source_url,
    fetched_at = EXCLUDED.fetched_at,
    records = EXCLUDED.records
"""


def main() -> None:
    sources = json.loads((TABLES / "sources.json").read_text(encoding="utf-8"))
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    with psycopg.connect(url) as connection:
        if connection.execute("SELECT to_regclass('data.sources')").fetchone()[0] is None:
            return
        for source in sources:
            table = sql.Identifier("data", source["table"])
            columns = sql.SQL(", ").join(sql.Identifier(c["name"]) for c in source["columns"])
            connection.execute(sql.SQL("TRUNCATE {}").format(table))
            # In the CSV format of COPY, an empty field without quotes is NULL.
            copy = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(table, columns)
            with connection.cursor().copy(copy) as writer:
                writer.write((TABLES / f"{source['table']}.csv").read_bytes())
            connection.execute(UPSERT_SOURCE, source)
    print(f"Loaded {len(sources)} tables into the schema data.")


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as error:
        sys.exit(f"Cannot connect to Postgres. Is it running (make up)?\n{error}")
