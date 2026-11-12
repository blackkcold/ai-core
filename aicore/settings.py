"""Environment-only runtime settings. Secrets are never serialized to clients."""
from __future__ import annotations

import os
import json
import re
from urllib.parse import urlsplit
from dataclasses import dataclass, field
from pathlib import Path


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "on", "yes"}


def _parse_budgets(raw: str, *, include_keyless_defaults: bool = True) -> dict[str, int]:
    budgets = {
        "wikipedia": 60, "hackernews": 50, "openalex": 40,
        "crossref": 40, "europepmc": 40, "stackoverflow": 30,
        "openlibrary": 30,
    } if include_keyless_defaults else {}
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
    search_enabled: tuple[str, ...] = (
        "wikipedia", "hackernews", "openalex", "crossref",
        "europepmc", "stackoverflow", "openlibrary",
    )
    search_daily_limits: dict[str, int] = field(default_factory=lambda: _parse_budgets(""))
    search_monthly_limits: dict[str, int] = field(default_factory=dict)
    search_allow_metered: bool = False
    llm_daily_limit: int = 0
    free_cloud_daily_limit: int = 20
    project_tokens: dict[str, str] = field(default_factory=dict)
    allowed_origins: tuple[str, ...] = ()
    search_cache_seconds: int = 3600
    timeout_seconds: int = 20

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        enabled = tuple(p.strip() for p in os.getenv("AI_CORE_SEARCH_ENABLED", "wikipedia,hackernews,openalex,crossref,europepmc,stackoverflow,openlibrary").split(",") if p.strip())
        monthly = _parse_budgets(os.getenv("AI_CORE_SEARCH_MONTHLY_LIMITS", ""), include_keyless_defaults=False)
        try:
            project_tokens = json.loads(os.getenv("AI_CORE_PROJECT_TOKENS", "{}"))
        except ValueError as exc:
            raise ValueError("AI_CORE_PROJECT_TOKENS must be a JSON object") from exc
        if not isinstance(project_tokens, dict):
            raise ValueError("AI_CORE_PROJECT_TOKENS must be a JSON object")
        for name, secret in project_tokens.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", name):
                raise ValueError("invalid project token name")
            if not isinstance(secret, str) or len(secret) < 24:
                raise ValueError("project tokens must contain at least 24 characters")
        if len(set(project_tokens.values())) != len(project_tokens):
            raise ValueError("project tokens must be unique")
        origins = tuple(x.strip() for x in os.getenv("AI_CORE_ALLOWED_ORIGINS", "").split(",") if x.strip())
        for origin in origins:
            url = urlsplit(origin)
            local = url.hostname in {"localhost", "127.0.0.1", "::1"}
            if (url.scheme != "https" and not (local and url.scheme == "http")) or (
                    not url.hostname or url.username or url.password or url.path not in {"", "/"} or
                    url.query or url.fragment or origin.rstrip("/") !=
                    (url.scheme + "://" + url.netloc)):
                raise ValueError("invalid AI_CORE_ALLOWED_ORIGINS origin")
        obj = cls(
            host=os.getenv("AI_CORE_HOST", defaults.host),
            port=int(os.getenv("AI_CORE_PORT", defaults.port)),
            token=os.getenv("AI_CORE_TOKEN", ""),
            state_db=os.getenv("AI_CORE_STATE_DB", defaults.state_db),
            search_enabled=enabled,
            search_daily_limits=_parse_budgets(os.getenv("AI_CORE_SEARCH_DAILY_LIMITS", "")),
            search_monthly_limits=monthly,
            search_allow_metered=truthy(os.getenv("AI_CORE_ALLOW_METERED_SEARCH", "0")),
            llm_daily_limit=int(os.getenv("AI_CORE_LLM_DAILY_LIMIT", "0")),
            free_cloud_daily_limit=int(os.getenv("AI_CORE_FREE_CLOUD_DAILY_LIMIT", "20")),
            project_tokens=project_tokens,
            allowed_origins=origins,
            search_cache_seconds=int(os.getenv("AI_CORE_SEARCH_CACHE_SECONDS", "3600")),
            timeout_seconds=int(os.getenv("AI_CORE_TIMEOUT_SECONDS", "20")),
        )
        if not 1 <= obj.port <= 65535:
            raise ValueError("invalid AI_CORE_PORT")
        if not 1 <= obj.timeout_seconds <= 120:
            raise ValueError("AI_CORE_TIMEOUT_SECONDS must be 1..120")
        if not 0 <= obj.search_cache_seconds <= 86400:
            raise ValueError("AI_CORE_SEARCH_CACHE_SECONDS must be 0..86400")
        if obj.llm_daily_limit < 0:
            raise ValueError("AI_CORE_LLM_DAILY_LIMIT cannot be negative")
        if obj.free_cloud_daily_limit < 0:
            raise ValueError("AI_CORE_FREE_CLOUD_DAILY_LIMIT cannot be negative")
        if obj.host not in {"127.0.0.1", "::1", "localhost"} and not (obj.token or obj.project_tokens):
            raise ValueError("AI_CORE_TOKEN is required when binding a non-loopback address")
        if obj.token and len(obj.token) < 24:
            raise ValueError("AI_CORE_TOKEN must be at least 24 characters")
        return obj

    @property
    def resolved_db(self) -> Path:
        return Path(self.state_db).expanduser().resolve()
