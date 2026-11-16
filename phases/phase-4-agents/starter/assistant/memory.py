"""Compaction and long-term memory. Week 12.

Compaction (step 2): when the context of a conversation gets near the limit
(get_settings().compact_at_tokens), summarise the messages with one model call, and start
a new context with the summary (conversations.start_new_context()). The next request
then holds the summary in place of the old messages, so it is shorter.

Long-term memory (step 3): the agent saves facts about a user with the tool save_memory.
A fact gets a vector from the embedding service of Phase 2 (assistant.embeddings.embed)
and goes into the table `memories`. With each new question, the agent finds the facts of
the same user that are closest to the question (pgvector, as in vector_search() of week 5),
and gives them to the model. A user never gets the facts of another user.

Change the signatures if your design needs other values.
"""

from __future__ import annotations

from typing import Any


def context_tokens(usage: Any) -> int:
    """The size of the context after a reply, from the usage of the reply.

    Count each part of the prompt: the input tokens, the tokens written to the cache and
    the tokens read from the cache. Add the output tokens, because the reply goes into the
    context too. (The other way is the token counting endpoint: client().messages.count_tokens.)
    """
    raise NotImplementedError("Week 12, step 2")


def compact(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarise the messages with one model call. Return the messages of the new context.

    Tell the model what the summary must keep (the questions, the dataset IDs and titles of
    the answers, the cited chunk IDs, the open questions) and what it can leave out (the
    raw tool results). Use call_claude(), so the call has its cost, its log line and its
    trace. The new context starts with the summary as a user message.
    """
    raise NotImplementedError("Week 12, step 2")


def save_fact(user: str, fact: str, conversation_id: str | None = None) -> int:
    """Embed the fact, store it in `memories` for the user, and return the ID of the row."""
    raise NotImplementedError("Week 12, step 3")


def search_facts(user: str, text: str, k: int | None = None) -> list[dict[str, Any]]:
    """The k saved facts of the user that are closest to the text, best first.

    Return a list of dicts with at least `id` and `text`. Search only the rows of this user.
    k defaults to get_settings().memory_results. When the user has no facts, return an
    empty list without a call to the embedding service.
    """
    raise NotImplementedError("Week 12, step 3")
