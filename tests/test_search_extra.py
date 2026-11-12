"""Offline API fixtures for explicitly enabled supplemental search backends."""
import os
import unittest
from unittest.mock import patch

from aicore.errors import InvalidRequest
from aicore.search import SearchQuery
from aicore.search_extra import EXTRA_SEARCH, search_extra, _safe_searxng_url


class Transport:
    def __init__(self):
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if "perplexity.ai" in url:
            return {"results": [{"url": "https://example.org/a", "title": "A",
                                 "snippet": "search result", "date": "2026-11-01"}]}
        if "ydc-index.io" in url:
            return {"results": {"web": [{"url": "https://example.org/b", "title": "B",
                                        "snippets": ["context"], "page_age": "2026-11-01"}]}}
        if "s.jina.ai" in url:
            return {"data": [{"url": "https://example.org/c", "title": "C",
                              "description": "search result"}]}
        if "newsapi.org" in url:
            return {"articles": [{"url": "https://example.org/d", "title": "D",
                                  "description": "article", "publishedAt": "2026-11-01T00:00:00Z"}]}
        if "127.0.0.1" in url:
            return {"results": [{"url": "https://example.org/e", "title": "E",
                                 "content": "self-hosted"}]}
        raise AssertionError("unexpected URL: " + url)


class ExtraSearchTests(unittest.TestCase):
    def test_optional_providers_have_live_contract_fixtures(self):
        self.assertEqual(len(EXTRA_SEARCH), 5)
        for provider in EXTRA_SEARCH:
            with self.subTest(provider=provider):
                fake = Transport()
                rows = search_extra(provider, SearchQuery(query="test"), "fakekey", fake, 10)
                self.assertTrue(rows)
                self.assertTrue(rows[0]["url"].startswith("https://"))
                self.assertTrue(EXTRA_SEARCH[provider]["docs"].startswith("https://"))

    def test_credentials_use_headers_not_query(self):
        fake = Transport()
        search_extra("you", SearchQuery(query="A"), "secret", fake, 10)
        self.assertEqual(fake.calls[0][2]["headers"]["X-API-Key"], "secret")
        self.assertNotIn("secret", fake.calls[0][1])
        fake = Transport()
        search_extra("newsapi", SearchQuery(query="B"), "secret", fake, 10)
        self.assertEqual(fake.calls[0][2]["headers"]["X-Api-Key"], "secret")

    def test_unverified_recency_is_rejected_not_silently_dropped(self):
        for provider in ("perplexity", "jina"):
            with self.assertRaises(InvalidRequest):
                search_extra(provider, SearchQuery(query="q", recency="7d"),
                             "test", Transport(), 10)
        with self.assertRaises(InvalidRequest):
            search_extra("you", SearchQuery(query="q", recency="90d"),
                         "test", Transport(), 10)

    def test_searxng_custom_url_restricted_to_loopback(self):
        with patch.dict(os.environ, {"AI_CORE_SEARXNG_URL": "https://example.com/search"}):
            with self.assertRaises(InvalidRequest):
                _safe_searxng_url()
        with patch.dict(os.environ, {"AI_CORE_SEARXNG_URL": "http://127.0.0.1:8081/search"}):
            self.assertEqual(_safe_searxng_url(), "http://127.0.0.1:8081/search")

    def test_newsapi_does_not_suggest_production_free_tier(self):
        self.assertIn("development-only", EXTRA_SEARCH["newsapi"]["note"])


if __name__ == "__main__":
    unittest.main()
