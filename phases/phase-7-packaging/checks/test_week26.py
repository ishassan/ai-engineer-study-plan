"""Week 26 checks: the trace ID of each answer, the feedback in Langfuse, and the architecture document.

Run them with `make check WEEK=26`. Postgres and Langfuse must run (`make up`). The model is the
fake Claude API of the lab, so the checks are free. The checks send questions through /ask, post
feedback to /feedback, and read the traces and the scores back through the public API of Langfuse.

Fixed names:

- The `done` event of /ask (and of /approve) has `trace_id`: the ID of the Langfuse trace of the
  request, 32 lowercase hexadecimal characters.
- `POST /feedback` takes the JSON body `{"trace_id": ..., "rating": "good" or "bad", "comment": ...}`.
  The comment is optional. A request needs a sign-in, as /ask does.
- The feedback is a Langfuse score on that trace, with the name `user-feedback`, the value 1 for
  good and 0 for bad (data type BOOLEAN or NUMERIC), and the comment of the request.
- `docs/architecture.md` keeps the sections of its template and the table of numbers.

One check stops the graph for an approval of register_dataset and approves it. It adds a dataset
with an ID that starts with `check-` to the catalogue, and deletes it at the end.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from typing import Any

import pytest

from labkit.capstone import ARCHITECTURE, REPO, document_problems
from labkit.fake_claude import answer_reply, tool_reply
from labkit.sse import AskResult, parse_sse

sys.path.insert(0, str(REPO / "phases" / "phase-4-agents" / "checks"))
import phase4_helpers as phase4  # the helpers of the approval flow of week 15

SCORE = "user-feedback"
TRACE_ID = re.compile(r"[0-9a-f]{32}")


def ask(client: Any, question: str, user: str = "analyst") -> AskResult:
    response = client.post("/ask", json={"question": question}, headers={"X-User": user})
    return AskResult(
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
        events=parse_sse(response.text) if response.status_code == 200 else [],
    )


def answered(client: Any, fake: Any) -> tuple[str, str]:
    """Ask one question with a unique mark. Return the mark and the trace ID of the `done` event."""
    mark = uuid.uuid4().hex[:12]
    fake.always(answer_reply(f"Two datasets show it (check {mark})."))
    result = ask(client, f"Which datasets show the electricity consumption by sector? (check {mark})")
    assert result.status_code == 200, f"/ask answered HTTP {result.status_code}."
    trace_id = result.done.get("trace_id")
    assert trace_id, (
        "The `done` event has no `trace_id`. Inside answer_events(), the current trace is the trace of "
        "the request: add its ID to the `done` event (step 2)."
    )
    assert TRACE_ID.fullmatch(str(trace_id)), f"`trace_id` must be 32 lowercase hex characters, not {trace_id!r}."
    return mark, trace_id


def scores_of(langfuse: Any, trace_id: str, count: int = 1) -> list[dict[str, Any]]:
    found = langfuse.wait_for(
        lambda: [s for s in langfuse.scores(trace_id) if s.get("name") == SCORE], lambda s: len(s) >= count
    )
    assert found, (
        f"Langfuse has no score `{SCORE}` on the trace {trace_id} after 45 s. Store the feedback with "
        "create_score() of the Langfuse client, with the trace ID of the request."
    )
    return found


def number(value: Any) -> float:
    return float(value) if not isinstance(value, bool) else float(int(value))


@pytest.fixture
def new_dataset(database):
    """The arguments of a register_dataset call for a new dataset. The row is deleted at the end."""
    import psycopg

    dataset_id = f"check-{uuid.uuid4().hex[:10]}"
    yield {
        "dataset_id": dataset_id,
        "title": f"Check dataset {dataset_id}",
        "description": "A dataset that a check of week 26 registers. The check deletes it at the end.",
        "owner": "Lab checks",
    }
    url = os.environ.get("DATABASE_URL", "postgresql://assistant:assistant@localhost:5432/assistant")
    with psycopg.connect(url, connect_timeout=3) as connection:
        connection.execute("DELETE FROM datasets WHERE id = %s", (dataset_id,))


# ---- step 2: the trace ID of each answer, and the feedback ----------------------------------


def test_each_answer_reports_the_id_of_its_trace(client, fake, langfuse):
    mark, trace_id = answered(client, fake)
    observations = langfuse.wait_for(lambda: langfuse.observations(trace_id), lambda found: bool(found))
    assert observations, (
        f"Langfuse has no trace {trace_id}. Send the ID of the current trace of the request, not a new ID."
    )
    assert any(mark in str(o.get("input") or "") for o in observations), (
        "The trace of `trace_id` does not hold the question of the request. Read the ID inside the "
        "request, with get_current_trace_id() of the Langfuse client."
    )


def test_the_graph_reports_the_id_of_its_trace(client, fake, langfuse, graph):
    mark, trace_id = answered(client, fake)
    observations = langfuse.wait_for(lambda: langfuse.observations(trace_id), lambda found: bool(found))
    assert any(mark in str(o.get("input") or "") for o in observations), (
        "With AGENT_IMPL=langgraph, the `trace_id` of the `done` event is not the trace of the request. "
        "The graph makes the `done` event too: add the trace ID there as well."
    )


def test_the_answer_after_an_approval_reports_the_id_of_its_trace(client, fake, langfuse, graph, new_dataset):
    mark = uuid.uuid4().hex[:12]
    fake.script(
        tool_reply(("register_dataset", new_dataset)),
        answer_reply(f"The dataset is registered (check {mark}).", tools_called=["register_dataset"]),
    )
    first = phase4.ask(client, "Please register this dataset in the catalogue.", user=phase4.new_user())
    assert first.status_code == 200 and first.of("approval"), (
        "The graph did not stop for an approval of register_dataset (Phase 4, week 15). "
        f"Events: {first.names}, errors: {first.errors}"
    )
    resumed = phase4.approve(client, first.done["conversation_id"], True, user="check-approver")
    assert resumed.status_code == 200, f"/approve answered HTTP {resumed.status_code}."
    trace_id = resumed.done.get("trace_id")
    assert trace_id, (
        "The `done` event of /approve has no `trace_id`. A user can rate the answer after an approval "
        "too: the graph makes this `done` event in the run after the approval, so add the trace ID there."
    )
    assert TRACE_ID.fullmatch(str(trace_id)), f"`trace_id` must be 32 lowercase hex characters, not {trace_id!r}."
    observations = langfuse.wait_for(
        lambda: langfuse.observations(trace_id), lambda found: any(mark in str(o.get("output") or "") for o in found)
    )
    assert any(mark in str(o.get("output") or "") for o in observations), (
        f"The trace {trace_id} of the `trace_id` of /approve does not hold the answer after the approval. "
        "Read the ID inside the request of /approve, with get_current_trace_id() of the Langfuse client."
    )


def test_good_feedback_is_a_score_with_its_comment(client, fake, langfuse):
    _, trace_id = answered(client, fake)
    comment = f"Clear answer, check {uuid.uuid4().hex[:8]}"
    response = client.post("/feedback", json={"trace_id": trace_id, "rating": "good", "comment": comment})
    assert response.is_success, f"POST /feedback answered HTTP {response.status_code}: {response.text[:300]}"
    score = scores_of(langfuse, trace_id)[0]
    assert number(score["value"]) == 1, f"The score of a good answer must be 1, not {score['value']!r}."
    assert score.get("comment") == comment, "The score must have the comment of the feedback."
    assert score.get("dataType") in {"BOOLEAN", "NUMERIC"}, (
        f"Use the data type BOOLEAN or NUMERIC, not {score.get('dataType')}."
    )


def test_bad_feedback_is_a_score_of_zero(client, fake, langfuse):
    _, trace_id = answered(client, fake)
    response = client.post("/feedback", json={"trace_id": trace_id, "rating": "bad"})
    assert response.is_success, f"POST /feedback without a comment answered HTTP {response.status_code}."
    scores = scores_of(langfuse, trace_id)
    assert [number(score["value"]) for score in scores] == [0], (
        f"A bad answer must get one score of 0. Found: {[score['value'] for score in scores]}."
    )


@pytest.mark.parametrize(
    "body",
    [
        {"trace_id": "0" * 32, "rating": "great"},
        {"trace_id": "not-a-trace", "rating": "good"},
        {"rating": "good"},
    ],
    ids=["unknown rating", "bad trace ID", "no trace ID"],
)
def test_feedback_refuses_a_bad_request(client, body):
    response = client.post("/feedback", json=body)
    assert response.status_code == 422, (
        f"POST /feedback with {body} must answer 422, not {response.status_code}. The rating is good or "
        "bad, and the trace ID has 32 hex characters."
    )


def test_feedback_needs_a_sign_in(client):
    body = {"trace_id": "0" * 32, "rating": "good"}
    response = client.post("/feedback", json=body, headers={"Authorization": ""})
    assert response.status_code == 401, (
        f"POST /feedback without a token must answer 401, not {response.status_code}. Use current_user(), as /ask does."
    )


# ---- steps 4 and 5: the architecture document -----------------------------------------------


def test_the_architecture_document_is_written():
    problems = document_problems(ARCHITECTURE, REPO)
    assert not problems, "docs/architecture.md is not complete:\n- " + "\n- ".join(problems)
