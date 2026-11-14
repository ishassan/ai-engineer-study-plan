"""Load data/catalogue.json into the tables datasets and dataset_columns.

You can run the script again at any time. It replaces the rows of each dataset
in the file. `make up` calls this script.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg

CATALOGUE = Path(__file__).resolve().parent.parent / "data" / "catalogue.json"
DEFAULT_URL = "postgresql://assistant:assistant@localhost:5432/assistant"

UPSERT_DATASET = """
INSERT INTO datasets (id, title, description, owner, themes, keywords, license,
                      update_frequency, updated_at, records_count, source_url)
VALUES (%(id)s, %(title)s, %(description)s, %(owner)s, %(themes)s, %(keywords)s, %(license)s,
        %(update_frequency)s, %(updated_at)s, %(records_count)s, %(source_url)s)
ON CONFLICT (id) DO UPDATE SET
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    owner = EXCLUDED.owner,
    themes = EXCLUDED.themes,
    keywords = EXCLUDED.keywords,
    license = EXCLUDED.license,
    update_frequency = EXCLUDED.update_frequency,
    updated_at = EXCLUDED.updated_at,
    records_count = EXCLUDED.records_count,
    source_url = EXCLUDED.source_url
"""

INSERT_COLUMN = """
INSERT INTO dataset_columns (dataset_id, position, name, label, data_type, description)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def main() -> None:
    datasets = json.loads(CATALOGUE.read_text())
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    with psycopg.connect(url) as connection:
        for dataset in datasets:
            connection.execute(UPSERT_DATASET, dataset)
            connection.execute("DELETE FROM dataset_columns WHERE dataset_id = %s", (dataset["id"],))
            for position, column in enumerate(dataset["columns"], start=1):
                connection.execute(
                    INSERT_COLUMN,
                    (
                        dataset["id"],
                        position,
                        column["name"],
                        column["label"],
                        column["data_type"],
                        column["description"],
                    ),
                )
    print(f"Loaded {len(datasets)} datasets.")


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as error:
        sys.exit(f"Cannot connect to Postgres. Is it running (make up)?\n{error}")
