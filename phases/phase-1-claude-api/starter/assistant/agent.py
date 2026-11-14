"""The answer to one question, as a stream of events. Weeks 1, 2 and 3.

answer_events() is the core of the project. The API sends each event that it
yields to the client. The function grows in each week:

Week 1: one request to Claude, no tools.
    ("text", {"text": "..."})   for each piece of text
    ("done", {...})             one time, at the end

Week 2: the model loop with tools.
    ("tool", {"name": ..., "input": {...}, "is_error": False})   for each tool call

Week 3: the typed answer.
    ("answer", {"answer": ..., "dataset_ids": [...], "tools_called": [...]})
    ("error", {"message": "..."})   when the answer is not valid
    No "text" events from week 3: the answer is JSON, so you validate it first.

The "done" event always comes last. Its data:
    model, input_tokens, output_tokens, cost_usd, latency_ms   (sums of all requests)
    requests   the number of requests to Claude
    stop       "final" when the model gave a final answer, "max_turns" when the loop gave up
"""

from __future__ import annotations

from typing import Any, Iterator

from assistant.config import get_settings  # noqa: F401 (you will use it)
from assistant.llm import stream_claude  # noqa: F401 (you will use it)

SYSTEM_PROMPT = "You answer questions about a catalogue of public datasets."


def answer_events(question: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Answer one question. Yield (event name, data) pairs as described above."""
    raise NotImplementedError("Week 1, step 4")
    yield  # This line makes the function a generator. Remove it with the line above.
