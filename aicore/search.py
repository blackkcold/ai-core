"""Six opt-in search providers with normalized evidence, failover, and quotas.

Default is keyless Tavily and Firecrawl only. The keyed API pathways can
consume money/credits: AI_CORE_ALLOW_METERED_SEARCH=1 and an explicit per-
provider daily limit are both required. We never assume a published free tier
guarantees no paid charges on the user's account.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from html import unescape
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from .errors import BudgetExceeded, InvalidRequest, MissingCredential, ProviderUnavailable, UpstreamError
from .settings import Settings
from .store import Store
from .transport import Transport


SEARCH_PROVIDERS = {
    "tavily": {"endpoint": "https://api.tavily.com/search", "env": "TAVILY_API_KEY",
               "auth": "optional", "docs": "https://docs.tavily.com/documentation/api-reference/endpoint/search"},
    "firecrawl": {"endpoint": "https://api.firecrawl.dev/v2/search", "env": "FIRECRAWL_API_KEY",
                  "auth": "optional", "docs": "https://docs.firecrawl.dev/api-reference/v2-endpoint/search"},
    "tinyfish": {"endpoint": "https://api.search.tinyfish.ai", "env": "TINYFISH_API_KEY",
                 "auth": "required", "docs": "https://tinyfish.ai/"},
    "exa": {"endpoint": "https://api.exa.ai/search", "env": "EXA_API_KEY",
            "auth": "required", "docs": "https://docs.exa.ai/reference/search"},
    "parallel": {"endpoint": "https://api.parallel.ai/v1/search", "env": "PARALLEL_API_KEY",
                 "auth": "required", "docs": "https://docs.parallel.ai/api-reference/search-api/search"},
    "brave": {"endpoint": "https://api.search.brave.com/res/v1/web/search", "env": "BRAVE_API_KEY",
              "auth": "required", "docs": "https://api-dashboard.search.brave.com/app/documentation/web-search"},
}
DEFAULT_ORDER = ("tavily", "firecrawl", "tinyfish", "parallel", "exa", "brave")
RECENCY_DAYS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}
_REGEX_TAG = re.compile(r"<[^>]*>")


def list_search_providers() -> list[dict]:
    return [{"id": k, **dict(v)} for k, v in SEARCH_PROVIDERS.items()]


def _text(value, length=4000) -> str:
    if not isinstance(value, str):
        return ""
    return unescape(_REGEX_TAG.sub(" ", value)).strip()[:length]


def _public_url(value) -> str | None:
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        p = urlsplit(value)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            return None
        if p.hostname in {"localhost", "127.0.0.1", "::1"} or p.hostname.endswith((".local", ".internal")):
            return None
        import ipaddress
        try:
            ip = ipaddress.ip_address(p.hostname)
            if not ip.is_global:
                return None
        except ValueError:
            pass
        return urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", p.query, ""))
    except ValueError:
        return None


def _canonical(url: str) -> str:
    p = urlsplit(url)
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
          if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((p.scheme, p.netloc.lower().removeprefix("www."), p.path.rstrip("/") or "/",
                       urlencode(sorted(qs)), ""))


@dataclass(frozen=True)
class SearchQuery:
    query: str
    limit: int = 6
    recency: str | None = None
    language: str | None = None
    provider: str | None = None
    mode: str = "free-first"
    max_attempts: int = 3

    @classmethod
    def parse(cls, data: dict):
        if not isinstance(data, dict):
            raise InvalidRequest("search request must be an object")
        query = data.get("query", "")
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 600:
            raise InvalidRequest("query must contain 1..600 characters")
        limit = data.get("limit", 6)
        attempts = data.get("max_attempts", 3)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise InvalidRequest("limit must be 1..20")
        if type(attempts) is not int or not 1 <= attempts <= 6:
            raise InvalidRequest("max_attempts must be 1..6")
        recency = data.get("recency")
        if recency is not None and recency not in RECENCY_DAYS:
            raise InvalidRequest("recency must be 24h,7d,30d,90d,1y or null")
        language = data.get("language")
        if language is not None and (not isinstance(language, str) or
                                     not re.fullmatch(r"[a-zA-Z]{2}(-[a-zA-Z]{2})?", language)):
            raise InvalidRequest("language must be a language code")
        provider = data.get("provider")
        if provider is not None and provider not in SEARCH_PROVIDERS:
            raise InvalidRequest("unknown search provider")
        mode = data.get("mode", "free-first")
        if mode not in {"free-first", "deep"}:
            raise InvalidRequest("mode must be free-first or deep")
        return cls(query.strip(), limit, recency, language, provider, mode, attempts)


def _get(obj, *keys):
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def _hits(provider: str, rows: list) -> list[dict]:
    results = []
    for index, item in enumerate(rows or []):
        if not isinstance(item, dict):
            continue
        url = _public_url(item.get("url"))
        if not url:
            continue
        item_text = item.get("snippet") or item.get("description") or item.get("content") or ""
        highlights = item.get("highlights") or item.get("excerpts")
        if isinstance(highlights, list) and highlights:
            item_text = "\n".join(str(x) for x in highlights)
        results.append({
            "url": url,
            "title": _text(item.get("title") or url, 500),
            "snippet": _text(item_text),
            "published_at": item.get("publishedDate") or item.get("published_date") or
                            item.get("publish_date") or item.get("date") or item.get("page_age"),
            "provider": provider,
            "rank": index + 1,
            "inline_content": _text(item.get("raw_content") or item.get("rawContent"), 24000) or None,
        })
    return results


def _call(provider: str, q: SearchQuery, key: str, transport: Transport, timeout: int) -> list[dict]:
    endpoint = SEARCH_PROVIDERS[provider]["endpoint"]
    if provider == "tavily":
        headers = {"Authorization": "Bearer " + key} if key else {"X-Tavily-Access-Mode": "keyless"}
        payload = {"query": q.query, "search_depth": "basic", "max_results": q.limit,
                   "include_raw_content": True, "include_answer": False,
                   "topic": "news" if q.recency else "general"}
        if q.recency:
            payload["days"] = RECENCY_DAYS[q.recency]
        data = transport.request_json("POST", endpoint, headers=headers, body=payload, timeout=timeout)
        return _hits(provider, data.get("results", []))
    if provider == "firecrawl":
        headers = {"Authorization": "Bearer " + key} if key else {}
        payload = {"query": q.query, "limit": q.limit}
        tbs = {"24h": "qdr:d", "7d": "qdr:w", "30d": "qdr:m", "1y": "qdr:y"}.get(q.recency)
        if tbs:
            payload["tbs"] = tbs
        data = transport.request_json("POST", endpoint, headers=headers, body=payload, timeout=timeout)
        return _hits(provider, _get(data, "data", "web") or data.get("web") or [])
    if not key:
        raise MissingCredential("missing key for " + provider)
    if provider == "tinyfish":
        params = {"query": q.query}
        if q.language:
            params["language"] = q.language[:2]
        if q.recency:
            params["recency_minutes"] = str(RECENCY_DAYS[q.recency] * 1440)
        data = transport.request_json("GET", endpoint + "?" + urlencode(params),
                                      headers={"X-API-Key": key}, timeout=timeout)
        return _hits(provider, data.get("results", []))[:q.limit]
    if provider == "exa":
        payload = {"query": q.query, "type": "auto", "numResults": q.limit,
                   "contents": {"highlights": True}}
        if q.recency:
            timestamp = datetime.now(timezone.utc) - timedelta(days=RECENCY_DAYS[q.recency])
            payload["startPublishedDate"] = timestamp.isoformat().replace("+00:00", "Z")
        data = transport.request_json("POST", endpoint, headers={"x-api-key": key},
                                      body=payload, timeout=timeout)
        return _hits(provider, data.get("results", []))
    if provider == "parallel":
        data = transport.request_json("POST", endpoint, headers={"x-api-key": key},
                                      body={"objective": q.query, "search_queries": [q.query], "mode": "fast"},
                                      timeout=timeout)
        return _hits(provider, data.get("results", []))[:q.limit]
    if provider == "brave":
        params = {"q": q.query, "count": str(q.limit), "text_decorations": "false"}
        freshness = {"24h": "pd", "7d": "pw", "30d": "pm", "1y": "py"}.get(q.recency)
        if freshness:
            params["freshness"] = freshness
        data = transport.request_json("GET", endpoint + "?" + urlencode(params),
                                      headers={"X-Subscription-Token": key}, timeout=timeout)
        return _hits(provider, _get(data, "web", "results") or [])
    raise InvalidRequest("unknown provider")


def _filter_recency(rows: list[dict], recency: str | None) -> list[dict]:
    if not recency:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENCY_DAYS[recency])
    result = []
    for item in rows:
        published = item["published_at"]
        if not isinstance(published, str):
            result.append(item)  # unknown date is disclosed, never presented as verified recency
            continue
        try:
            parsed = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed >= cutoff:
                result.append(item)
        except ValueError:
            result.append(item)
    return result


class SearchRouter:
    def __init__(self, settings: Settings, store: Store, transport: Transport | None = None):
        self.settings, self.store = settings, store
        self.transport = transport or Transport()

    def search(self, raw: dict, tenant: str = "local") -> dict:
        q = SearchQuery.parse(raw)
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", tenant):
            raise InvalidRequest("invalid tenant")
        enabled = [p for p in DEFAULT_ORDER if p in self.settings.search_enabled]
        if q.provider:
            if q.provider not in enabled:
                raise InvalidRequest("provider is disabled")
            enabled = [q.provider]
        key_data = {"tenant": tenant, "query": q.query, "limit": q.limit, "recency": q.recency,
                    "lang": q.language, "providers": enabled, "mode": q.mode,
                    "metered": self.settings.search_allow_metered}
        cache_key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
        cached = self.store.cache_get(cache_key)
        if cached:
            return {**cached, "cached": True, "attempts": 0}
        attempted, failures, all_hits, used, warnings = 0, [], [], [], []
        for provider in enabled:
            if attempted >= q.max_attempts:
                break
            spec = SEARCH_PROVIDERS[provider]
            key = os.getenv(spec["env"], "").strip()
            if not self.settings.search_allow_metered:
                if spec["auth"] == "required":
                    failures.append({"provider": provider, "reason": "metered_disabled"})
                    continue
                key = ""  # opt into metered mode even if a key is present
            if spec["auth"] == "required" and not key:
                failures.append({"provider": provider, "reason": "missing_key"})
                continue
            if self.store.cooldown(provider):
                failures.append({"provider": provider, "reason": "cooldown"})
                continue
            if provider not in self.settings.search_daily_limits:
                failures.append({"provider": provider, "reason": "missing_budget"})
                continue
            try:
                attempt = self.store.reserve(
                    provider, tenant, self.settings.search_daily_limits[provider],
                    self.settings.search_monthly_limits.get(provider))
            except BudgetExceeded:
                failures.append({"provider": provider, "reason": "local_budget_exceeded"})
                continue
            attempted += 1
            try:
                hits = _call(provider, q, key, self.transport, self.settings.timeout_seconds)
                self.store.finish(attempt, "success")
                if q.recency in {"90d"} and provider in {"firecrawl", "brave"}:
                    warnings.append(provider + ": no equivalent upstream 90-day filter; locally filtered dated results")
                hits = _filter_recency(hits, q.recency)
                if hits:
                    used.append(provider)
                    all_hits.extend(hits)
                    if q.mode == "free-first":
                        break
                else:
                    failures.append({"provider": provider, "reason": "empty"})
            except UpstreamError as exc:
                self.store.finish(attempt, "http_" + str(exc.status_code))
                failures.append({"provider": provider, "reason": "http_" + str(exc.status_code)})
                if exc.status_code in (402, 429):
                    self.store.set_cooldown(provider, exc.retry_after or (86400 if exc.status_code == 402 else 60))
            except (ProviderUnavailable, InvalidRequest) as exc:
                self.store.finish(attempt, "error")
                failures.append({"provider": provider, "reason": exc.code})
        unique = []
        seen = set()
        for hit in all_hits:
            canonical = _canonical(hit["url"])
            if canonical not in seen:
                seen.add(canonical)
                unique.append(hit)
        out = {"query": q.query, "hits": unique[:q.limit], "providers": used,
               "attempts": attempted, "cached": False, "failures": failures, "warnings": warnings,
               "date_filter_note": "Undated results may not satisfy the requested recency" if q.recency else None}
        if unique:
            self.store.cache_put(cache_key, out, self.settings.search_cache_seconds)
            return out
        if attempted == 0:
            raise ProviderUnavailable("no search provider is eligible; check configuration, keys and budgets")
        return out  # return empty hits with provider-specific failure provenance
