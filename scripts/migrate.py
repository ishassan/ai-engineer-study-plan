"""Apply the SQL files in db/migrations that the database does not have yet.

Each file runs once, in the order of its name. The table schema_migrations
records the files that ran. `make up` calls this script.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"
DEFAULT_URL = "postgresql://assistant:assistant@localhost:5432/assistant"


def main() -> None:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    with psycopg.connect(url) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {row[0] for row in connection.execute("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            connection.execute(path.read_text())
            connection.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            connection.commit()
            print(f"Applied {path.name}")
    print("The database schema is up to date.")


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as error:
        sys.exit(f"Cannot connect to Postgres. Is it running (make up)?\n{error}")
