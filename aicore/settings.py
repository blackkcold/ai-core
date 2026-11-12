"""Environment-only runtime settings. Secrets are never serialized to clients."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "on", "yes"}


def _parse_budgets(raw: str) -> dict[str, int]:
    budgets = {"tavily": 100, "firecrawl": 40}
    if not raw.strip():
        return budgets
    for part in raw.split(","):
        provider, sep, value = part.strip().partition("=")
        if not sep or not provider or not value.isdecimal():
            raise ValueError("AI_CORE_SEARCH_DAILY_LIMITS must use provider=nonnegative_integer")
        budgets[provider] = int(value)
    return budgets


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = ""
    state_db: str = "./.ai-core-state.sqlite3"
    search_enabled: tuple[str, ...] = ("tavily", "firecrawl")
    search_daily_limits: dict[str, int] = field(default_factory=lambda: {"tavily": 100, "firecrawl": 40})
    search_monthly_limits: dict[str, int] = field(default_factory=dict)
    search_allow_metered: bool = False
    search_cache_seconds: int = 3600
    timeout_seconds: int = 20

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        enabled = tuple(p.strip() for p in os.getenv("AI_CORE_SEARCH_ENABLED", "tavily,firecrawl").split(",") if p.strip())
        monthly = _parse_budgets(os.getenv("AI_CORE_SEARCH_MONTHLY_LIMITS", "")) if os.getenv("AI_CORE_SEARCH_MONTHLY_LIMITS") else {}
        obj = cls(
            host=os.getenv("AI_CORE_HOST", defaults.host),
            port=int(os.getenv("AI_CORE_PORT", defaults.port)),
            token=os.getenv("AI_CORE_TOKEN", ""),
            state_db=os.getenv("AI_CORE_STATE_DB", defaults.state_db),
            search_enabled=enabled,
            search_daily_limits=_parse_budgets(os.getenv("AI_CORE_SEARCH_DAILY_LIMITS", "")),
            search_monthly_limits=monthly,
            search_allow_metered=truthy(os.getenv("AI_CORE_ALLOW_METERED_SEARCH", "0")),
            search_cache_seconds=int(os.getenv("AI_CORE_SEARCH_CACHE_SECONDS", "3600")),
            timeout_seconds=int(os.getenv("AI_CORE_TIMEOUT_SECONDS", "20")),
        )
        if not 1 <= obj.port <= 65535:
            raise ValueError("invalid AI_CORE_PORT")
        if not 1 <= obj.timeout_seconds <= 120:
            raise ValueError("AI_CORE_TIMEOUT_SECONDS must be 1..120")
        if not 0 <= obj.search_cache_seconds <= 86400:
            raise ValueError("AI_CORE_SEARCH_CACHE_SECONDS must be 0..86400")
        if obj.host not in {"127.0.0.1", "::1", "localhost"} and not obj.token:
            raise ValueError("AI_CORE_TOKEN is required when binding a non-loopback address")
        if obj.token and len(obj.token) < 24:
            raise ValueError("AI_CORE_TOKEN must be at least 24 characters")
        return obj

    @property
    def resolved_db(self) -> Path:
        return Path(self.state_db).expanduser().resolve()
