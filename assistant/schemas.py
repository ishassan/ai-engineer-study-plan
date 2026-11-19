"""Reference solution."""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    document_title: str = Field(description="The title of the document, as search_documents returned it.")
    page: int = Field(description="The page number, as search_documents returned it.")
    chunk_id: str = Field(description="The chunk_id of the passage, copied exactly from the tool result.")


class Answer(BaseModel):
    answer: str = Field(description="The answer to the user, in plain text.")
    dataset_ids: list[str] = Field(
        description="The id of each dataset that the answer uses. Only ids that a tool returned."
    )
    tools_called: list[str] = Field(description="The name of each tool that you called.")
    citations: list[Citation] = Field(
        default_factory=list,
        description=(
            "One item for each passage of search_documents that supports the answer. Empty "
            "when the answer uses no document."
        ),
    )
