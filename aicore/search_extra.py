"""Opt-in external search services and a loopback-only self-hosted SearXNG adapter.

None of these are silently enabled. Keyed plans can consume money/credits;
NewsAPI's developer tier is legally restricted to development environments.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, quote, urlsplit

from .errors import InvalidRequest


EXTRA_SEARCH = {
    "perplexity": {
        "endpoint": "https://api.perplexity.ai/search",
        "env": "PERPLEXITY_API_KEY", "auth": "required",
        "docs": "https://docs.perplexity.ai/docs/search/quickstart",
        "categories": ["general", "news", "research"],
        "supports_recency": False,
    },
    "you": {
        "endpoint": "https://ydc-index.io/v1/search",
        "env": "YDC_API_KEY", "auth": "required",
        "docs": "https://you.com/docs/guides/search",
        "categories": ["general", "news"],
        "supports_recency": True,
    },
    "jina": {
        "endpoint": "https://s.jina.ai/search",
        "env": "JINA_API_KEY", "auth": "required",
        "docs": "https://docs.jina.ai/",
        "categories": ["general", "research"],
        "supports_recency": False,
    },
    "newsapi": {
        "endpoint": "https://newsapi.org/v2/everything",
        "env": "NEWSAPI_API_KEY", "auth": "required",
        "docs": "https://newsapi.org/docs/endpoints/everything",
        "categories": ["news"],
        "supports_recency": True,
        "note": "Free developer plan is development-only; not authorized for production.",
    },
    "searxng": {
        "endpoint": "http://127.0.0.1:8081/search",
        "env": "", "auth": "none",
        "docs": "https://docs.searxng.org/dev/search_api.html",
        "categories": ["general", "news", "research", "developer"],
        "supports_recency": True,
        "note": "Requires a self-hosted loopback instance with JSON output enabled.",
    },
}

RECENCY = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}


def _cutoff(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _safe_searxng_url():
    url = os.getenv("AI_CORE_SEARXNG_URL", "http://127.0.0.1:8081/search")
    parts = urlsplit(url)
    if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
            or not parts.port or parts.username or parts.password or
            parts.query or parts.fragment or parts.path != "/search"):
        raise InvalidRequest("AI_CORE_SEARXNG_URL must use loopback HTTP with /search")
    return url


def search_extra(provider, q, key, transport, timeout) -> list[dict]:
    if provider not in EXTRA_SEARCH:
        raise InvalidRequest("unknown extra search provider")
    if provider in {"perplexity", "jina"} and q.recency:
        raise InvalidRequest("upstream cannot reliably enforce requested recency")
    if provider == "you":
        params = {"query": q.query, "count": q.limit}
        freshness = {"24h": "day", "7d": "week", "30d": "month",
                     "1y": "year"}.get(q.recency)
        if freshness:
            params["freshness"] = freshness
        if q.recency == "90d":
            raise InvalidRequest("You.com search cannot guarantee a 90-day filter")
        if q.language:
            params["language"] = q.language.upper()
        data = transport.request_json("POST", EXTRA_SEARCH[provider]["endpoint"],
            headers={"X-API-Key": key}, body=params, timeout=timeout)
        web = (data.get("results") or {}).get("web") or []
        return [{"url": r.get("url"), "title": r.get("title"),
                 "snippet": " ".join(r.get("snippets") or []) or r.get("description") or "",
                 "date": r.get("page_age")} for r in web if isinstance(r, dict)]

    if provider == "perplexity":
        params = {"query": q.query, "max_results": q.limit}
        if q.language:
            params["search_language_filter"] = [q.language.split("-")[0].lower()]
        data = transport.request_json("POST", EXTRA_SEARCH[provider]["endpoint"],
            headers={"Authorization": "Bearer " + key}, body=params, timeout=timeout)
        return [r for r in data.get("results", []) if isinstance(r, dict)]

    if provider == "jina":
        params = {"q": q.query, "num": q.limit}
        if q.language:
            params["hl"] = q.language.split("-")[0]
        data = transport.request_json("POST", EXTRA_SEARCH[provider]["endpoint"],
            headers={"Authorization": "Bearer " + key, "Accept": "application/json",
                     "X-Respond-With": "no-content"}, body=params, timeout=timeout)
        rows = data.get("data") or data.get("results") or []
        return [r for r in rows if isinstance(r, dict)]

    if provider == "newsapi":
        params = {"q": q.query[:500], "pageSize": q.limit, "sortBy": "publishedAt"}
        if q.recency:
            params["from"] = _cutoff(RECENCY[q.recency])
        if q.language:
            params["language"] = q.language.split("-")[0]
        data = transport.request_json("GET", EXTRA_SEARCH[provider]["endpoint"]
            + "?" + urlencode(params), headers={"X-Api-Key": key}, timeout=timeout)
        return [{"url": r.get("url"), "title": r.get("title"),
                 "snippet": r.get("description") or r.get("content") or "",
                 "published_date": r.get("publishedAt")}
                for r in data.get("articles", []) if isinstance(r, dict)]

    if provider == "searxng":
        params = {"q": q.query, "format": "json", "pageno": 1}
        if q.language:
            params["language"] = q.language
        if q.recency:
            time_range = {"24h": "day", "30d": "month", "1y": "year"}.get(q.recency)
            if not time_range:
                raise InvalidRequest("SearXNG cannot guarantee requested recency")
            params["time_range"] = time_range
        data = transport.request_json("GET", _safe_searxng_url() + "?" + urlencode(params),
                                      timeout=timeout)
        return [{"url": r.get("url"), "title": r.get("title"),
                 "snippet": r.get("content") or "", "published_date": r.get("publishedDate")}
                for r in data.get("results", []) if isinstance(r, dict)]
    raise InvalidRequest("unknown extra search provider")
