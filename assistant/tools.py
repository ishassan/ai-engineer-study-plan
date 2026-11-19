"""Reference solution: the tools of Phase 2 and save_memory."""

from __future__ import annotations

import json
from typing import Any

from assistant.db import query
from assistant.retrieval import retrieve

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
    {
        "name": "search_documents",
        "description": (
            "Search the text of the methodology and quality reports of the General Authority "
            "for Statistics, in English and Arabic. Use it for questions about how a statistic "
            "is made: definitions of terms, data sources, sample design, base years, units and "
            "reference periods. Do not use it to find a dataset: use search_datasets for that. "
            "Write the query as a full question in the language of the user. The tool returns "
            "the best passages, each with its chunk_id, the title of the document, the page and "
            "the text. Cite a passage with exactly these three values."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question, in English or Arabic."},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of passages to return. Default 5, maximum 10.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save one fact about the user in the long-term memory, so that you know it in later "
            "conversations. Use it when the user tells you something about themselves or their "
            "work that will help later answers: their team, their task, the datasets that they "
            "use, how they want the answers. Write the fact as one full sentence about the user. "
            "Do not save facts about the catalogue: the tools give those."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "One sentence, for example 'The user works on water statistics.'"},
            },
            "required": ["fact"],
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


def search_documents(query_text: str, limit: int = 5) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 10))
    return [
        {"chunk_id": row["chunk_id"], "title": row["title"], "page": row["page"], "text": row["text"]}
        for row in retrieve(query_text, "rerank", limit)
    ]


def run_tool(
    name: str, tool_input: dict[str, Any], user: str = "anonymous", conversation_id: str | None = None
) -> str:
    if name == "save_memory":
        from assistant.memory import save_fact

        fact_id = save_fact(user, tool_input["fact"], conversation_id)
        return json.dumps({"saved": True, "id": fact_id})
    if name == "search_datasets":
        result: Any = search_datasets(tool_input["query"], tool_input.get("limit", 5))
    elif name == "get_dataset_schema":
        result = get_dataset_schema(tool_input["dataset_id"])
    elif name == "get_dataset_stats":
        result = get_dataset_stats(tool_input["dataset_id"])
    elif name == "search_documents":
        result = search_documents(tool_input["query"], tool_input.get("limit", 5))
    else:
        raise ValueError(f"Unknown tool: {name}")
    return json.dumps(result, ensure_ascii=False)
