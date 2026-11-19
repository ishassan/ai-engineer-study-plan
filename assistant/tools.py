"""Reference solution."""

from __future__ import annotations

import json
from typing import Any

from assistant.db import query

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_datasets",
        "description": (
            "Search the dataset catalogue by topic. Use this tool first, when you do not know "
            "which datasets exist for a subject. The query is matched against the title, "
            "description, keywords, themes and owner of each dataset. Write the query as a few "
            "keywords, for example 'crude oil production' or 'water consumption region'. The "
            "tool returns the best matches with their id, title, owner, themes and a short "
            "description. It returns an empty list when nothing matches: then try other words."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords that describe the subject."},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of datasets to return. Default 5, maximum 20.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_dataset_schema",
        "description": (
            "Get the columns of one dataset: the name, label, data type and description of each "
            "column. Use it when the user asks what a dataset contains or which fields it has, "
            "or when you must check that a dataset has the data that the question needs. The "
            "dataset_id must be an id that search_datasets returned. Do not guess an id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "The id of the dataset."},
            },
            "required": ["dataset_id"],
        },
    },
    {
        "name": "get_dataset_stats",
        "description": (
            "Get the facts about one dataset: the number of records, the number of columns, the "
            "date of the last update, the update frequency, the owner and the license. Use it "
            "for questions about size, freshness or ownership. The dataset_id must be an id that "
            "search_datasets returned. Do not guess an id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "The id of the dataset."},
            },
            "required": ["dataset_id"],
        },
    },
]

SEARCH_SQL = """
WITH docs AS (
    SELECT d.*,
           setweight(to_tsvector('english', title), 'A')
           || setweight(to_tsvector('english', array_to_string(keywords || themes, ' ')), 'B')
           || setweight(to_tsvector('english', description || ' ' || owner), 'C') AS doc
    FROM datasets d
), q AS (
    SELECT replace(plainto_tsquery('english', %(query)s)::text, '&', '|')::tsquery AS tsq
)
SELECT id, title, owner, themes, left(description, 300) AS description,
       ts_rank(doc, tsq) AS score
FROM docs, q
WHERE doc @@ tsq
ORDER BY score DESC, id
LIMIT %(limit)s
"""


def search_datasets(query_text: str, limit: int = 5) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 20))
    rows = query(SEARCH_SQL, {"query": query_text, "limit": limit})
    for row in rows:
        row["score"] = round(row["score"], 4)
    return rows


def _dataset(dataset_id: str) -> dict[str, Any]:
    rows = query("SELECT * FROM datasets WHERE id = %s", (dataset_id,))
    if not rows:
        raise LookupError(
            f"No dataset has the id {dataset_id!r}. Use search_datasets to find a correct id."
        )
    return rows[0]


def get_dataset_schema(dataset_id: str) -> dict[str, Any]:
    dataset = _dataset(dataset_id)
    columns = query(
        "SELECT name, label, data_type, description FROM dataset_columns "
        "WHERE dataset_id = %s ORDER BY position",
        (dataset_id,),
    )
    return {"id": dataset["id"], "title": dataset["title"], "columns": columns}


def get_dataset_stats(dataset_id: str) -> dict[str, Any]:
    dataset = _dataset(dataset_id)
    count = query("SELECT count(*) AS n FROM dataset_columns WHERE dataset_id = %s", (dataset_id,))
    return {
        "id": dataset["id"],
        "title": dataset["title"],
        "owner": dataset["owner"],
        "license": dataset["license"],
        "records_count": dataset["records_count"],
        "columns_count": count[0]["n"],
        "updated_at": dataset["updated_at"].isoformat(),
        "update_frequency": dataset["update_frequency"],
    }


def run_tool(name: str, tool_input: dict[str, Any]) -> str:
    if name == "search_datasets":
        result: Any = search_datasets(tool_input["query"], tool_input.get("limit", 5))
    elif name == "get_dataset_schema":
        result = get_dataset_schema(tool_input["dataset_id"])
    elif name == "get_dataset_stats":
        result = get_dataset_stats(tool_input["dataset_id"])
    else:
        raise ValueError(f"Unknown tool: {name}")
    return json.dumps(result, ensure_ascii=False)
