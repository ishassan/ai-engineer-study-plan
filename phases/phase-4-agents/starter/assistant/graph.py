"""The agent as a LangGraph graph. Week 14.

The graph does what your loop in agent.py does, with the same tools, the same memory and
the same planner, and it gives the same events:

    plan, tool, answer, error, done

With AGENT_IMPL=langgraph the service uses answer_events() of this file. With PROVIDER
you choose the model (models.py), and the graph does not change.

The nodes that you need: a model node (the chat model with the tools and the schema of
the answer), a tool node (run_tool() for each tool call, with a `tool` event for each), a
planner node and a node that changes the plan, the memory (the history of the
conversation, the saved facts, compaction), and one plain-code node: the citations. The
model gives the chunk ID of each passage that it cites, and plain code adds the title
and the page from the results of search_documents. The citation rule of week 7 stays: a
cited chunk ID that no search of this request returned is rejected, and the model is
asked again one time.

Send the events of a node with get_stream_writer() (langgraph.config), and read them
in answer_events() with stream_mode="custom". Pass the Langfuse callback handler
(langfuse.langchain.CallbackHandler) in the config of the run, so each model call is a
generation of the trace.
"""

from __future__ import annotations

from typing import Any, Iterator


def build_graph():
    """Build and compile the graph."""
    raise NotImplementedError("Week 14, step 2")


def answer_events(
    question: str, conversation_id: str | None = None, user: str = "anonymous"
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Run the graph for one question, and yield the same events as agent.py."""
    raise NotImplementedError("Week 14, step 2")
