"""The typed answer of the assistant. Week 3.

Define a Pydantic model with the name Answer and these fields:

    answer        str         the answer text for the user
    dataset_ids   list[str]   the id of each dataset that the answer uses
    tools_called  list[str]   the name of each tool that the model called

Give each field a description. The API sends the descriptions to the model as
part of the JSON schema, so they work like a small prompt.
"""

from pydantic import BaseModel, Field  # noqa: F401 (you will use them)
