"""Reference solution."""

from pydantic import BaseModel, Field


class Answer(BaseModel):
    answer: str = Field(description="The answer to the user, in plain text.")
    dataset_ids: list[str] = Field(
        description="The id of each dataset that the answer uses. Only ids that a tool returned."
    )
    tools_called: list[str] = Field(description="The name of each tool that you called.")
