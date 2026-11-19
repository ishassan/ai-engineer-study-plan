"""The MCP server for read-only SQL queries. Phase 4, week 16.

Start it on your machine with

    uv run python -m assistant.servers.sql_server

`make up` starts it in Docker as the service `mcp-sql` (profile phase4). The agent connects
to http://localhost:8091/mcp (the setting MCP_SQL_URL). The server uses the transport
"streamable HTTP" of the official MCP Python SDK.

The server is given. Your work is the tool run_sql and its safety:

- Connect with get_settings().sql_database_url: the read-only role of your migration.
- Refuse each statement that changes data, also a change in a CTE or after a semicolon.
- Refuse each table that is not on your list of allowed tables: the tables of the schema
  `data` and the catalogue tables `datasets` and `dataset_columns`.
- Return at most get_settings().sql_row_limit rows (the setting SQL_ROW_LIMIT).
- Stop a query after get_settings().sql_timeout_seconds (the setting SQL_TIMEOUT_SECONDS).

The checks call the tool with an MCP client. The result must be a JSON object with the
keys `rows` (a list with one item for each row) and `truncated` (true when the rows were cut
at the limit). For a refused or a failed query, raise an exception with a clear message: the
SDK sends it to the client as an error result.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "sql",
    instructions="Read-only SQL on the data tables and the catalogue tables of the data platform.",
    # Docker sets MCP_HOST=0.0.0.0, so that the other containers can connect.
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8091")),
    # Each request is complete in itself, and the reply is one JSON body (no event stream).
    stateless_http=True,
    json_response=True,
)


# The docstring of a tool function is the description that the model gets. Write it for
# the model: when to use the tool, which tables there are, and the limits.
@mcp.tool()
def run_sql(query: str) -> dict[str, Any]:
    """Run one read-only SQL query (PostgreSQL) on the data tables and return the rows."""
    raise NotImplementedError("Week 16, step 3")


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
