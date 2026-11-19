"""The chat models of the two providers, for the graph of week 14.

The graph in graph.py uses the LangChain chat model interface, so the same graph runs on
Claude (ChatAnthropic of langchain-anthropic) and on OpenAI (ChatOpenAI of
langchain-openai). The setting PROVIDER chooses one. The model names come from the
settings: get_settings().model and get_settings().openai_model.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage


def chat_model(provider: str | None = None) -> BaseChatModel:
    """The chat model of the provider (default: get_settings().provider).

    Give each model the max_tokens of the settings. Two traps:
    - When OPENAI_BASE_URL is set (the checks set it), ChatOpenAI leaves out the token
      usage of a streamed reply of the Chat Completions API. Ask for it with
      stream_usage=True.
    - The anthropic SDK makes its own trace span for each call when a tracer is
      registered, and the Langfuse callback makes one too. ChatAnthropic makes its client
      itself, so turn the SDK span off with the environment variable
      ANTHROPIC_OPEN_TELEMETRY=false.
    """
    raise NotImplementedError("Week 14, step 2")


def usage_of(message: AIMessage) -> dict[str, Any]:
    """The usage of one model call in the fields of the `done` event, with its cost.

    Return model, input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens and cost_usd. LangChain gives the usage in
    message.usage_metadata: its input_tokens holds all input tokens, with the cache reads
    and writes in input_token_details. The `done` event of your loop gives the input tokens
    without the cache tokens, as the Claude API does.
    """
    raise NotImplementedError("Week 14, step 2")
