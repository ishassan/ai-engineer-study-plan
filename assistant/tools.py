"""The tools that the model can call. Week 2.

A tool has two parts: the definition that the model reads (name, description,
input schema), and the Python function that does the work. The model sees only
the definition, so the description decides when and how the model uses the tool.
"""

from __future__ import annotations

from typing import Any

from assistant.db import query  # noqa: F401 (you will use it)

# The tool definitions, in the format of the `tools` parameter of the Messages API.
# Each tool needs: "name", "description" and "input_schema" (a JSON Schema object).
#   search_datasets      required input: query (string). Optional: limit (integer).
#   get_dataset_schema   required input: dataset_id (string).
#   get_dataset_stats    required input: dataset_id (string).
TOOLS: list[dict[str, Any]] = []


def search_datasets(query_text: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return the datasets that match the words best: id, title, and what helps the model choose."""
    raise NotImplementedError("Week 2, step 2")


def get_dataset_schema(dataset_id: str) -> dict[str, Any]:
    """Return the columns of one dataset: name, label, data type and description."""
    raise NotImplementedError("Week 2, step 2")


def get_dataset_stats(dataset_id: str) -> dict[str, Any]:
    """Return the facts of one dataset: records, columns, last update, owner."""
    raise NotImplementedError("Week 2, step 2")


def run_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Run the tool that the model asked for and return its result as a JSON string.

    Raise an exception when the tool does not exist, when the input is wrong, or
    when the dataset does not exist. The loop sends the message of the exception
    to the model, so write a message that helps the model correct its call.
    """
    raise NotImplementedError("Week 2, step 2")
