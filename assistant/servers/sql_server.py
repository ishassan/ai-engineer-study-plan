"""Reference solution: the MCP server for read-only SQL, with sign-in (week 19)."""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

import psycopg
from mcp.server.fastmcp import FastMCP
from psycopg import sql

from assistant.auth import caller, mcp_auth
from assistant.config import get_settings

PORT = int(os.environ.get("MCP_PORT", "8091"))

mcp = FastMCP(
    "sql",
    instructions="Read-only SQL on the data tables and the catalogue tables of the data platform.",
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=PORT,
    stateless_http=True,
    json_response=True,
    # Week 19: each request needs a token of the realm for the audience mcp-sql.
    **mcp_auth(get_settings().mcp_sql_audience, PORT),
)

# Each table of the schema `data`, and the two tables of the catalogue.
ALLOWED_SCHEMAS = {"data"}
ALLOWED_TABLES = {("public", "datasets"), ("public", "dataset_columns")}


def _nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def _check_plan(cursor: psycopg.Cursor, statement: str) -> None:
    """Refuse a statement that changes data or reads a table outside the list.

    EXPLAIN plans the statement without running it. A plan holds each table that the
    statement reads, also in a subquery, a CTE or a view. prepare=True sends the text as one
    prepared statement, so Postgres refuses a text with two statements.
    """
    cursor.execute(f"EXPLAIN (VERBOSE, FORMAT JSON) {statement}", prepare=True)
    plan = cursor.fetchone()[0][0]["Plan"]
    for node in _nodes(plan):
        if node["Node Type"] == "ModifyTable":
            raise ValueError("Refused: the query changes data. Only SELECT queries are allowed.")
        if "Relation Name" in node:
            table = (node.get("Schema"), node["Relation Name"])
            if table[0] not in ALLOWED_SCHEMAS and table not in ALLOWED_TABLES:
                raise ValueError(f"Refused: the table {table[0]}.{table[1]} is not in the list of allowed tables.")


@mcp.tool()
def run_sql(query: str) -> dict[str, Any]:
    """Run one read-only SQL query (PostgreSQL) on the data tables and return the rows.

    Use it when a question needs numbers from the records of a dataset. The schema `data` has
    one table for each of eight datasets of the catalogue. The table data.sources gives the
    dataset_id of each table. First call get_dataset_schema for the columns of the dataset, then
    write one SELECT on data.<table>. The catalogue tables datasets and dataset_columns can be
    read too. The result has at most a fixed number of rows (truncated is true when the result
    was cut): use WHERE, GROUP BY and LIMIT to keep the result small.
    """
    settings = get_settings()
    identity = caller()
    statement = query.strip().rstrip(";").strip()
    with psycopg.connect(settings.sql_database_url, connect_timeout=5) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            # SET LOCAL lasts until the end of the transaction. The role cannot call set_config(),
            # so the query of the model cannot change these values (migration 0010).
            for name, value in (("statement_timeout", f"{int(settings.sql_timeout_seconds * 1000)}ms"),
                                ("app.user", identity.user), ("app.groups", ",".join(identity.groups))):
                cursor.execute(sql.SQL("SET LOCAL {} = {}").format(sql.Identifier(name), sql.Literal(value)))
            try:
                _check_plan(cursor, statement)
                cursor.execute(statement, prepare=True)
                rows = cursor.fetchmany(settings.sql_row_limit + 1)
            except psycopg.errors.QueryCanceled as error:
                raise ValueError(f"The query took longer than {settings.sql_timeout_seconds:g} seconds and was stopped.") from error
            except psycopg.Error as error:
                raise ValueError(f"Postgres refused the query: {str(error).strip()}") from error
            columns = [column.name for column in cursor.description or []]
        connection.rollback()
    truncated = len(rows) > settings.sql_row_limit
    rows = json.loads(json.dumps([list(row) for row in rows[: settings.sql_row_limit]], default=str))
    return {"columns": columns, "rows": rows, "truncated": truncated}


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
