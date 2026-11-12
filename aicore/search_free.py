"""Public, credential-free *specialist* search providers.

These sources are not interchangeable with general web crawlers. Calls are
bounded by the SearchRouter's configured quota and provider-specific scope.
Remote metadata may be inaccurate; citations should still be verified.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

from .errors import InvalidRequest


PUBLIC_SEARCH = {
    "wikipedia": {
        "endpoint": "https://en.wikipedia.org/w/api.php",
        "docs": "https://www.mediawiki.org/wiki/API:Search",
        "categories": ["general"],
        "recency": False,
    },
    "hackernews": {
        "endpoint": "https://hn.algolia.com/api/v1/search",
        "docs": "https://hn.algolia.com/about",
        "categories": ["news", "developer"],
        "recency": True,
    },
    "openalex": {
        "endpoint": "https://api.openalex.org/works",
        "docs": "https://help.openalex.org/api/",
        "categories": ["research"],
        "recency": True,
    },
    "crossref": {
        "endpoint": "https://api.crossref.org/works",
        "docs": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
        "categories": ["research"],
        "recency": True,
    },
    "europepmc": {
        "endpoint": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        "docs": "https://europepmc.org/RestfulWebService",
        "categories": ["research"],
        "recency": True,
    },
    "stackoverflow": {
        "endpoint": "https://api.stackexchange.com/2.3/search/advanced",
        "docs": "https://api.stackexchange.com/docs/advanced-search",
        "categories": ["developer"],
        "recency": True,
    },
    "openlibrary": {
        "endpoint": "https://openlibrary.org/search.json",
        "docs": "https://openlibrary.org/dev/docs/api/search",
        "categories": ["books"],
        "recency": False,
    },
}

WIKI_LANGUAGES = frozenset({"en", "zh", "fr", "de", "es", "ja", "ko", "it", "pt", "ru"})


def _date(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _timestamp(days: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())


def _year_date(value) -> str | None:
    if not isinstance(value, list) or not value or not isinstance(value[0], list):
        return None
    parts = value[0]
    if not parts or not isinstance(parts[0], int):
        return None
    try:
        return datetime(parts[0], parts[1] if len(parts) > 1 else 1,
                        parts[2] if len(parts) > 2 else 1, tzinfo=timezone.utc).date().isoformat()
    except (ValueError, TypeError):
        return None


def _get(obj: dict, *keys):
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def _request(transport, endpoint: str, params: dict, timeout: int) -> dict:
    return transport.request_json("GET", endpoint + "?" + urlencode(params),
                                  timeout=timeout)


def search_public(provider, q, transport, timeout: int) -> list[dict]:
    """Convert each provider's JSON contract to common raw search rows.

    SearchRouter subsequently normalizes URLs, snippets and deduplicates.
    """
    if provider not in PUBLIC_SEARCH:
        raise InvalidRequest("unknown public search source")
    if q.recency and not PUBLIC_SEARCH[provider]["recency"]:
        raise InvalidRequest("this source cannot verify publication recency")
    days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(q.recency)
    query, count = q.query, q.limit

    if provider == "wikipedia":
        lang = (q.language or "en").split("-")[0].lower()
        if lang not in WIKI_LANGUAGES:
            raise InvalidRequest("unsupported Wikipedia language")
        base = "https://" + lang + ".wikipedia.org/w/api.php"
        data = _request(transport, base, {
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": count, "format": "json", "utf8": "1",
        }, timeout)
        rows = _get(data, "query", "search") or []
        return [{"url": "https://" + lang + ".wikipedia.org/?curid=" + str(row["pageid"]),
                 "title": row.get("title", ""), "snippet": row.get("snippet", "")}
                for row in rows if isinstance(row, dict) and isinstance(row.get("pageid"), int)]

    if provider == "hackernews":
        params = {"query": query, "hitsPerPage": count}
        endpoint = "https://hn.algolia.com/api/v1/search_by_date" if days else PUBLIC_SEARCH[provider]["endpoint"]
        if days:
            params["numericFilters"] = "created_at_i>" + str(_timestamp(days))
        data = _request(transport, endpoint, params, timeout)
        return [{"url": r.get("url") or ("https://news.ycombinator.com/item?id=" + str(r.get("objectID", ""))),
                 "title": r.get("title") or r.get("story_title") or "",
                 "snippet": r.get("story_text") or r.get("comment_text") or "",
                 "date": r.get("created_at")}
                for r in data.get("hits", []) if isinstance(r, dict)]

    if provider == "openalex":
        params = {"search": query, "per_page": count}
        if days:
            params["filter"] = "from_publication_date:" + _date(days)
        data = _request(transport, PUBLIC_SEARCH[provider]["endpoint"], params, timeout)
        return [{"url": r.get("doi") or r.get("id") or "",
                 "title": r.get("display_name") or r.get("title") or "",
                 "snippet": "OpenAlex research work",
                 "published_date": r.get("publication_date")}
                for r in data.get("results", []) if isinstance(r, dict)]

    if provider == "crossref":
        params = {"query.bibliographic": query, "rows": count}
        if days:
            params["filter"] = "from-pub-date:" + _date(days)
        data = _request(transport, PUBLIC_SEARCH[provider]["endpoint"], params, timeout)
        rows = _get(data, "message", "items") or []
        return [{"url": r.get("URL") or ("https://doi.org/" + str(r.get("DOI", ""))),
                 "title": (r.get("title") or [""])[0] if isinstance(r.get("title"), list) else "",
                 "snippet": r.get("container-title", [""])[0] if isinstance(r.get("container-title"), list) and r.get("container-title") else "",
                 "published_date": _year_date((r.get("published") or r.get("issued") or {}).get("date-parts"))}
                for r in rows if isinstance(r, dict)]

    if provider == "europepmc":
        search = "(" + query + ")"
        if days:
            search += " AND FIRST_PDATE:[" + _date(days) + " TO *]"
        data = _request(transport, PUBLIC_SEARCH[provider]["endpoint"],
                        {"query": search, "format": "json", "pageSize": count}, timeout)
        rows = _get(data, "resultList", "result") or []
        return [{"url": ("https://doi.org/" + r["doi"]) if r.get("doi")
                        else ("https://europepmc.org/articles/" + r["pmcid"]) if r.get("pmcid")
                        else ("https://europepmc.org/article/" + str(r.get("source", "MED")) + "/" + str(r.get("id", ""))),
                 "title": r.get("title", ""),
                 "snippet": r.get("journalTitle", ""), "published_date": r.get("firstPublicationDate")}
                for r in rows if isinstance(r, dict)]

    if provider == "stackoverflow":
        params = {"site": "stackoverflow", "q": query, "pagesize": count, "sort": "relevance"}
        if days:
            params["fromdate"] = _timestamp(days)
        data = _request(transport, PUBLIC_SEARCH[provider]["endpoint"], params, timeout)
        return [{"url": r.get("link", ""), "title": r.get("title", ""),
                 "snippet": "Stack Overflow question, score: " + str(r.get("score", 0)),
                 "date": datetime.fromtimestamp(r["creation_date"], timezone.utc).isoformat()
                         if isinstance(r.get("creation_date"), int) else None}
                for r in data.get("items", []) if isinstance(r, dict)]

    if provider == "openlibrary":
        params = {"q": query, "limit": count,
                  "fields": "key,title,author_name,first_publish_year"}
        if q.language:
            params["lang"] = q.language.split("-")[0].lower()
        data = _request(transport, PUBLIC_SEARCH[provider]["endpoint"], params, timeout)
        return [{"url": "https://openlibrary.org" + str(r.get("key", "")),
                 "title": r.get("title", ""),
                 "snippet": ", ".join(str(a) for a in (r.get("author_name") or [])[:3])}
                for r in data.get("docs", []) if isinstance(r, dict)
                and str(r.get("key", "")).startswith("/works/")]
    raise InvalidRequest("unknown public search source")
