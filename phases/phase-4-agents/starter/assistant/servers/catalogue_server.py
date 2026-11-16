"""The MCP server for the catalogue tools and register_dataset. Phase 4, week 16.

Start it on your machine with

    uv run python -m assistant.servers.catalogue_server

`make up` starts it in Docker as the service `mcp-catalogue` (profile phase4). The agent
connects to http://localhost:8092/mcp (the setting MCP_CATALOGUE_URL).

The server is given. Your work is the four tools. Each tool has the name and the arguments
of the tool in assistant/tools.py, so the model sees no change. Use the functions that you
wrote in assistant/tools.py, and give each tool the description of its definition there.

register_dataset runs only after a person approves it. The approval stays in the graph: the
server does not know the user, so the graph pauses before it calls the tool, and the graph
writes the audit log.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "catalogue",
    instructions="Search the dataset catalogue of the data platform, and register new datasets.",
    # Docker sets MCP_HOST=0.0.0.0, so that the other containers can connect.
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("MCP_PORT", "8092")),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def search_datasets(query: str, limit: int = 5) -> Any:
    """Search the catalogue."""
    raise NotImplementedError("Week 16, step 2")


@mcp.tool()
def get_dataset_schema(dataset_id: str) -> Any:
    """The columns of one dataset."""
    raise NotImplementedError("Week 16, step 2")


@mcp.tool()
def get_dataset_stats(dataset_id: str) -> Any:
    """The record count and the update time of one dataset."""
    raise NotImplementedError("Week 16, step 2")


@mcp.tool()
def register_dataset(dataset_id: str, title: str, description: str, owner: str, source_url: str = "") -> Any:
    """Register a new dataset in the catalogue."""
    raise NotImplementedError("Week 16, step 2")


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
