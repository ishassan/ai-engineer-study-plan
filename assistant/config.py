"""Settings of the service. Each setting comes from an environment variable.

This is the Phase 6 copy of the file. It adds the settings of the model gateway (week 21) to
the Phase 5 copy.

Call get_settings() each time you need a value. Do not keep the result in a
module-level constant: the checks change the environment between tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# US dollars for one million tokens.
# Claude Haiku 5.5, for prompts up to 100,000 tokens. A longer prompt pays higher prices.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (November 2026).
# GPT-6 Luna, standard processing. "cache_write_5m" holds the price of the 30-minute cache
# write. Source: https://developers.openai.com/api/docs/pricing (November 2026).
PRICES_PER_MTOK = {
    "claude-haiku-5-5": {
        "input": 0.10,
        "output": 0.50,
        "cache_write_5m": 0.125,
        "cache_read": 0.01,
    },
    "gpt-6-luna": {
        "input": 0.10,
        "output": 0.50,
        "cache_write_5m": 0.125,
        "cache_read": 0.01,
    },
}

AGENT_IMPLEMENTATIONS = ("handwritten", "langgraph")
PROVIDERS = ("anthropic", "openai")


@dataclass(frozen=True)
class Settings:
    database_url: str
    model: str
    max_tokens: int
    max_turns: int
    response_cache: bool
    response_cache_dir: Path
    request_log_path: Path
    # Phase 4
    agent_impl: str
    provider: str
    openai_model: str
    compact_at_tokens: int
    planner: bool
    memory_results: int
    mcp_sql_url: str
    mcp_catalogue_url: str
    sql_database_url: str
    sql_row_limit: int
    sql_timeout_seconds: float
    # Phase 5
    auth_issuer: str
    auth_metadata_url: str
    auth_client_id: str
    auth_client_secret: str
    auth_scope: str
    api_audience: str
    mcp_sql_audience: str
    mcp_catalogue_audience: str
    guardrails_url: str
    guardrails_config_id: str
    # Phase 6
    gateway_url: str
    gateway_key: str


def _choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = os.environ.get(name, default).strip().lower()
    if value not in allowed:
        raise ValueError(f"{name}={value!r} is not valid. Use one of: {', '.join(allowed)}.")
    return value


def get_settings() -> Settings:
    env = os.environ
    issuer = env.get("AUTH_ISSUER", "http://localhost:8180/realms/lab").rstrip("/")
    return Settings(
        database_url=env.get(
            "DATABASE_URL", "postgresql://assistant:assistant@localhost:5432/assistant"
        ),
        model=env.get("CLAUDE_MODEL", "claude-haiku-5-5"),
        max_tokens=int(env.get("CLAUDE_MAX_TOKENS", "4096")),
        max_turns=int(env.get("AGENT_MAX_TURNS", "8")),
        response_cache=env.get("RESPONSE_CACHE", "on").lower() != "off",
        response_cache_dir=Path(env.get("RESPONSE_CACHE_DIR", ROOT / ".cache" / "responses")),
        request_log_path=Path(env.get("REQUEST_LOG_PATH", ROOT / "logs" / "requests.jsonl")),
        # Week 14: the loop that answers (your loop of agent.py, or the graph of graph.py),
        # and the provider of the model for the graph. The hand-written loop uses Claude only.
        agent_impl=_choice("AGENT_IMPL", "handwritten", AGENT_IMPLEMENTATIONS),
        provider=_choice("PROVIDER", "anthropic", PROVIDERS),
        openai_model=env.get("OPENAI_MODEL", "gpt-6-luna"),
        # Week 12: compact the conversation when its context reaches this number of tokens.
        # The default stays below 100,000 tokens, where Claude Haiku 5.5 gets more expensive.
        compact_at_tokens=int(env.get("COMPACT_AT_TOKENS", "80000")),
        # Week 13: "on" makes the agent write a plan before it works on the question.
        planner=env.get("AGENT_PLANNER", "off").lower() == "on",
        # Week 12: the number of saved facts that the agent gives the model with a question.
        memory_results=int(env.get("MEMORY_RESULTS", "5")),
        # Week 16: the addresses of the two MCP servers. Compose gives the API container the
        # addresses inside the Docker network.
        mcp_sql_url=env.get("MCP_SQL_URL", "http://localhost:8091/mcp"),
        mcp_catalogue_url=env.get("MCP_CATALOGUE_URL", "http://localhost:8092/mcp"),
        # Week 16: the SQL server connects as the read-only role of your migration, cuts each
        # result at sql_row_limit rows, and stops a query after sql_timeout_seconds.
        sql_database_url=env.get(
            "SQL_DATABASE_URL",
            "postgresql://assistant_reader:assistant_reader@localhost:5432/assistant",
        ),
        sql_row_limit=int(env.get("SQL_ROW_LIMIT", "200")),
        sql_timeout_seconds=float(env.get("SQL_TIMEOUT_SECONDS", "5")),
        # Week 19: the authorization server (Keycloak, realm `lab`). AUTH_ISSUER is the exact
        # `iss` of its tokens. AUTH_METADATA_URL is where a server reads the metadata (and from
        # it the signing keys); inside Docker it can name another host than the issuer.
        auth_issuer=issuer,
        auth_metadata_url=env.get("AUTH_METADATA_URL", f"{issuer}/.well-known/openid-configuration"),
        # Week 19: the client of the jobs that run without a person (make testset, make
        # agent-eval). It gets a token with the client credentials grant.
        auth_client_id=env.get("AUTH_CLIENT_ID", "assistant-service"),
        auth_client_secret=env.get("AUTH_CLIENT_SECRET", "assistant-service-secret"),
        # Week 19: the scope that each server requires, and the audience that each one accepts.
        auth_scope=env.get("AUTH_SCOPE", "mcp:tools"),
        api_audience=env.get("API_AUDIENCE", "assistant-api"),
        mcp_sql_audience=env.get("MCP_SQL_AUDIENCE", "mcp-sql"),
        mcp_catalogue_audience=env.get("MCP_CATALOGUE_AUDIENCE", "mcp-catalogue"),
        # Week 20: the NeMo Guardrails server. Empty: the API makes no input and output checks.
        guardrails_url=env.get("GUARDRAILS_URL", "").rstrip("/"),
        guardrails_config_id=env.get("GUARDRAILS_CONFIG_ID", "assistant"),
        # Week 21: the LiteLLM gateway and the virtual key of the assistant. Empty GATEWAY_URL:
        # the model calls go directly to the providers, with ANTHROPIC_API_KEY and OPENAI_API_KEY.
        # With a gateway, the model names (CLAUDE_MODEL, OPENAI_MODEL) are the names of its routes.
        gateway_url=env.get("GATEWAY_URL", "").rstrip("/"),
        gateway_key=env.get("GATEWAY_KEY", ""),
    )
