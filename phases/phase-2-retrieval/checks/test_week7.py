"""Week 7 checks: the document search as a tool, the citations, and the rule that
rejects a citation that no tool result holds.

Run them with `make check WEEK=7`. They use the fake Claude API on localhost, so
they are free. Postgres, the embedding service and the re-ranking service must
run on your machine (`make up`), because the tool does a real search.
"""

from __future__ import annotations

import json

import pytest
from test_week5 import excerpt, sample_chunks

from labkit.fake_claude import json_reply, last_user_text, tool_reply
from labkit.sse import ask

QUESTION = "How does the General Authority for Statistics define a road?"
SEARCH = ("search_documents", {"query": "definition of a road in the land transport statistics"})
TOOL_NAMES = {"search_datasets", "get_dataset_schema", "get_dataset_stats", "search_documents"}
UNKNOWN_ID = "gastat-no-such-document-en:p1:c1"


def result_list(output: str) -> list[dict]:
    """The list of results in the output of search_documents."""
    data = json.loads(output)
    if isinstance(data, dict):
        data = next((value for value in data.values() if isinstance(value, list)), [])
    return [item for item in data if isinstance(item, dict) and "chunk_id" in item]


def returned_chunks(body: dict) -> list[dict]:
    """Each result of search_documents in the messages of a request."""
    chunks = []
    for message in body["messages"]:
        content = message.get("content")
        for block in [] if isinstance(content, str) else content:
            if block.get("type") != "tool_result" or block.get("is_error"):
                continue
            text = block["content"] if isinstance(block["content"], str) else block["content"][0]["text"]
            try:
                chunks.extend(result_list(text))
            except json.JSONDecodeError:
                pass
    return chunks


def answer(citations: list[dict]) -> dict:
    return {
        "answer": "A road is an open transportation route for the use of motorized vehicles.",
        "dataset_ids": [],
        "tools_called": ["search_documents"],
        "citations": citations,
    }


def cite(chunk: dict) -> dict:
    return {"document_title": chunk["title"], "page": chunk["page"], "chunk_id": chunk["chunk_id"]}


def good_answer(body: dict):
    """The model cites the first two chunks that the tool returned."""
    chunks = returned_chunks(body)
    assert chunks, "No tool result of the request holds a result of search_documents."
    return json_reply(answer([cite(chunk) for chunk in chunks[:2]]))


def wrong_answer(body: dict):
    """The model cites one chunk of the tool result and one chunk id that it invented."""
    chunks = returned_chunks(body)
    return json_reply(
        answer([cite(chunks[0]), {"document_title": "No such document", "page": 1, "chunk_id": UNKNOWN_ID}])
    )


# ---- step 2: the tool and the citations -----------------------------------------------------


def test_the_search_documents_tool_is_defined():
    from assistant.tools import TOOLS

    by_name = {tool["name"]: tool for tool in TOOLS}
    # Later phases add tools, so the check accepts more than these four.
    assert TOOL_NAMES <= set(by_name), "Add the tool search_documents to TOOLS, and keep the three tools of Phase 1."
    tool = by_name["search_documents"]
    assert len(tool["description"]) >= 150, (
        "The model now has two search tools. Say in the description when to use this one and "
        "not search_datasets, and what the tool returns."
    )
    assert "query" in tool["input_schema"]["required"]
    assert tool["input_schema"]["properties"]["query"].get("description")


@pytest.mark.parametrize("language", ["en", "ar"])
def test_search_documents_returns_chunks_with_title_and_page(language, chunks, sql, services):
    from assistant.tools import run_tool

    chunk = sample_chunks(sql, language, 1)[0]
    output = run_tool("search_documents", {"query": excerpt(chunk["text"], 10, 50)})
    assert isinstance(output, str), "run_tool returns a JSON string."
    results = result_list(output)
    assert 1 <= len(results) <= 10, (
        "Return the best chunks only, as a JSON list of objects with chunk_id, title, page and "
        "text. A tool result goes into the prompt, and you pay for each token of it."
    )
    stored = {
        row["id"]: row
        for row in sql(
            "SELECT c.id, c.page, d.title FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.id = ANY(%s)",
            ([result["chunk_id"] for result in results],),
        )
    }
    for result in results:
        assert {"chunk_id", "title", "page", "text"} <= set(result)
        assert result["chunk_id"] in stored, f"{result['chunk_id']} is not the id of a chunk."
        assert (result["page"], result["title"]) == (
            stored[result["chunk_id"]]["page"],
            stored[result["chunk_id"]]["title"],
        )
    assert chunk["id"] in stored, "The search with 40 words of a chunk must return this chunk."


def test_the_answer_model_has_citations_with_a_default():
    from assistant.schemas import Answer

    old = Answer.model_validate({"answer": "Text.", "dataset_ids": [], "tools_called": []})
    assert list(old.citations) == [], "An answer without citations must stay valid, as in Phase 1."
    new = Answer.model_validate(
        answer([{"document_title": "A report", "page": 7, "chunk_id": "gastat-land-transport-en:p7:c2"}])
    )
    citation = new.model_dump()["citations"][0]
    assert citation == {"document_title": "A report", "page": 7, "chunk_id": "gastat-land-transport-en:p7:c2"}
    with pytest.raises(Exception):
        Answer.model_validate(answer([{"document_title": "A report", "page": 7}]))


def test_the_request_has_the_four_tools_and_the_schema_of_the_citations(client, fake):
    ask(client, QUESTION)
    body = fake.last_request

    assert TOOL_NAMES <= {tool["name"] for tool in body["tools"]}
    schema = body["output_config"]["format"]["schema"]
    assert "citations" in schema["properties"], "Send the new schema of Answer in output_config."
    text = json.dumps(schema)
    for name in ("document_title", "page", "chunk_id"):
        assert f'"{name}"' in text, f"The schema of a citation needs the field {name}."


def test_an_answer_without_citations_is_valid(client, fake):
    fake.script(json_reply({"answer": "Text.", "dataset_ids": [], "tools_called": []}))
    result = ask(client, QUESTION)

    assert result.errors == []
    assert result.answer is not None and result.answer.get("citations", []) == []


def test_an_answer_with_citations_from_the_tool_result_is_accepted(client, fake, chunks, services):
    fake.script(tool_reply(SEARCH), good_answer)
    result = ask(client, QUESTION)

    assert result.errors == [], result.errors
    assert [tool["name"] for tool in result.tools] == ["search_documents"]
    assert len(fake.requests) == 2
    cited = returned_chunks(fake.requests[1])[:2]
    assert result.answer is not None, "Send the answer with its citations as the `answer` event."
    assert result.answer["citations"] == [cite(chunk) for chunk in cited]
    assert result.done["stop"] == "final"


# ---- step 3: reject a citation that the tool did not return ------------------------------------


def test_a_citation_that_no_tool_returned_is_rejected_and_the_model_is_asked_again(
    client, fake, chunks, services
):
    fake.script(tool_reply(SEARCH), wrong_answer, good_answer)
    result = ask(client, QUESTION)

    assert len(fake.requests) == 3, (
        "The second reply cites a chunk id that the tool did not return. Do not send this "
        "answer to the user. Ask the model again."
    )
    retry = fake.requests[2]
    assert [m["role"] for m in retry["messages"]][-2:] == ["assistant", "user"], (
        "Keep the rejected answer in the messages as an assistant turn, and add a user message "
        "after it."
    )
    assert UNKNOWN_ID in last_user_text(retry), "Tell the model which chunk ids were wrong."
    assert result.answer is not None, "The third reply is correct, so the stream has an `answer` event."
    assert UNKNOWN_ID not in json.dumps(result.answer)
    assert len(result.answer["citations"]) == 2
    assert result.errors == []
    assert result.done["requests"] == 3 and result.done["stop"] == "final"
    assert result.names[-2:] == ["answer", "done"]


def test_a_chunk_that_exists_but_was_not_returned_is_rejected(client, fake, chunks, sql, services):
    def cites_a_chunk_of_the_database(body):
        returned = {chunk["chunk_id"] for chunk in returned_chunks(body)}
        row = sql(
            "SELECT c.id, c.page, d.title FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE NOT (c.id = ANY(%s)) ORDER BY md5(c.id) LIMIT 1",
            (sorted(returned),),
        )[0]
        return json_reply(answer([{"document_title": row["title"], "page": row["page"], "chunk_id": row["id"]}]))

    fake.script(tool_reply(SEARCH), cites_a_chunk_of_the_database, good_answer)
    result = ask(client, QUESTION)

    assert len(fake.requests) == 3, (
        "The cited chunk is in the database, but no tool result of this conversation holds it. "
        "Compare the citations with the tool results, and not with the table."
    )
    assert result.answer is not None and result.errors == []


def test_a_second_wrong_answer_gives_an_error_event(client, fake, chunks, services):
    fake.script(tool_reply(SEARCH), wrong_answer, wrong_answer)
    fake.always(wrong_answer)
    result = ask(client, QUESTION)

    assert len(fake.requests) == 3, "Ask again one time only. Then stop."
    assert result.answer is None, "Do not send an answer with a wrong citation to the user."
    assert result.errors, "Send an `error` event when the second answer is wrong too."
    assert result.done["requests"] == 3  # The stream still ends with `done`.


def test_a_citation_without_any_search_is_rejected(client, fake):
    invented = answer([{"document_title": "No such document", "page": 1, "chunk_id": UNKNOWN_ID}])
    fake.script(json_reply(invented), json_reply({"answer": "Text.", "dataset_ids": [], "tools_called": []}))
    result = ask(client, QUESTION)

    assert len(fake.requests) == 2, "The model cited a chunk and did not search. Reject the answer."
    assert UNKNOWN_ID in last_user_text(fake.requests[1])
    assert result.answer is not None and result.errors == []
