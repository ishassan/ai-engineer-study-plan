"""Settings of the service. Each setting comes from an environment variable.

Call get_settings() each time you need a value. Do not keep the result in a
module-level constant: the checks change the environment between tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# US dollars for one million tokens, for prompts up to 100,000 tokens.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (November 2026).
PRICES_PER_MTOK = {
    "claude-haiku-5-5": {
        "input": 0.10,
        "output": 0.50,
        "cache_write_5m": 0.125,
        "cache_read": 0.01,
    },
}


@dataclass(frozen=True)
class Settings:
    database_url: str
    model: str
    max_tokens: int
    max_turns: int
    response_cache: bool
    response_cache_dir: Path
    request_log_path: Path


def get_settings() -> Settings:
    env = os.environ
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
    )
