"""Reference solution: the MCP server for the catalogue, with sign-in (week 19)."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from assistant import tools
from assistant.auth import mcp_auth
from assistant.config import get_settings

PORT = int(os.environ.get("MCP_PORT", "8092"))

mcp = FastMCP(
    "catalogue",
    instructions="Search the dataset catalogue of the data platform, and register new datasets.",
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=PORT,
    stateless_http=True,
    json_response=True,
    # Week 19: each request needs a token of the realm for the audience mcp-catalogue.
    **mcp_auth(get_settings().mcp_catalogue_audience, PORT),
)


def _description(name: str) -> str:
    definitions = [*tools.TOOLS, tools.REGISTER_DATASET]
    return next(tool["description"] for tool in definitions if tool["name"] == name)


@mcp.tool(description=_description("search_datasets"))
def search_datasets(query: str, limit: int = 5) -> str:
    return json.dumps(tools.search_datasets(query, limit), ensure_ascii=False)


@mcp.tool(description=_description("get_dataset_schema"))
def get_dataset_schema(dataset_id: str) -> str:
    return json.dumps(tools.get_dataset_schema(dataset_id), ensure_ascii=False)


@mcp.tool(description=_description("get_dataset_stats"))
def get_dataset_stats(dataset_id: str) -> str:
    return json.dumps(tools.get_dataset_stats(dataset_id), ensure_ascii=False)


@mcp.tool(description=_description("register_dataset"))
def register_dataset(dataset_id: str, title: str, description: str, owner: str, source_url: str = "") -> str:
    return json.dumps(tools.register_dataset(dataset_id, title, description, owner, source_url))


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
