import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from aicore.errors import BudgetExceeded, InvalidRequest, ProviderUnavailable, UpstreamError
from aicore.search import SearchQuery, SearchRouter
from aicore.settings import Settings
from aicore.store import Store


class FakeTransport:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = failures or {}

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        name = "tavily" if "tavily" in url else "firecrawl" if "firecrawl" in url else (
            "exa" if "exa.ai" in url else "brave" if "brave.com" in url else (
            "parallel" if "parallel.ai" in url else "tinyfish"))
        if name in self.failures:
            raise self.failures[name]
        row = {"url": "https://example.com/a?utm_source=x", "title": "Example",
               "content": "Article snippet"}
        if name == "firecrawl":
            return {"data": {"web": [{"url": "https://example.com/a", "title": "Example",
                                      "description": "Article snippet"}]}}
        return {"results": [row]}

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.cfg = replace(Settings(), search_daily_limits={
            "tavily": 2, "firecrawl": 3, "tinyfish": 2, "parallel": 2,
            "exa": 2, "brave": 2}, search_cache_seconds=3600)

    def tearDown(self):
        self.store.close()

    def test_cache_and_usage(self):
        fake = FakeTransport()
        router = SearchRouter(self.cfg, self.store, fake)
        first = router.search({"query": "test query"})
        second = router.search({"query": "test query"})
        self.assertEqual(first["providers"], ["tavily"])
        self.assertEqual(first["attempts"], 1)
        self.assertTrue(second["cached"])
        self.assertEqual(second["attempts"], 0)
        self.assertEqual(len(fake.calls), 1)

    def test_fallback_429_and_cooldown(self):
        fake = FakeTransport({"tavily": UpstreamError(429, retry_after=120)})
        router = SearchRouter(self.cfg, self.store, fake)
        r = router.search({"query": "fallback"})
        self.assertEqual(r["providers"], ["firecrawl"])
        self.assertEqual(r["attempts"], 2)
        self.assertGreater(self.store.cooldown("tavily"), 0)

    def test_no_metered_by_default_even_with_key(self):
        cfg = replace(self.cfg, search_enabled=("exa",))
        with patch.dict(os.environ, {"EXA_API_KEY": "test_key"}):
            with self.assertRaises(ProviderUnavailable):
                SearchRouter(cfg, self.store, FakeTransport()).search({"query": "test"})

    def test_explicit_keyed_provider(self):
        cfg = replace(self.cfg, search_enabled=("exa",), search_allow_metered=True)
        fake = FakeTransport()
        with patch.dict(os.environ, {"EXA_API_KEY": "test_key"}):
            result = SearchRouter(cfg, self.store, fake).search({"query": "test"})
        self.assertEqual(result["providers"], ["exa"])
        self.assertEqual(fake.calls[0][2]["headers"]["x-api-key"], "test_key")

    def test_90day_firecrawl_does_not_use_30day_upstream(self):
        cfg = replace(self.cfg, search_enabled=("firecrawl",))
        fake = FakeTransport()
        result = SearchRouter(cfg, self.store, fake).search({"query": "months", "recency": "90d"})
        self.assertIn("90-day", result["warnings"][0])
        self.assertNotIn("tbs", fake.calls[0][2]["body"])

    def test_default_disables_key_even_if_set(self):
        fake = FakeTransport()
        with patch.dict(os.environ, {"TAVILY_API_KEY": "key_should_not_be_sent"}):
            SearchRouter(self.cfg, self.store, fake).search({"query": "free"})
        self.assertIn("X-Tavily-Access-Mode", fake.calls[0][2]["headers"])
        self.assertNotIn("Authorization", fake.calls[0][2]["headers"])

    def test_invalid_query(self):
        for body in ({"query": ""}, {"query": "yes", "limit": 0},
                     {"query": "yes", "provider": "fake"},
                     {"query": "yes", "recency": "90 years"}):
            with self.assertRaises(InvalidRequest):
                SearchQuery.parse(body)

    def test_quota_is_transactional_under_threads(self):
        def reserve(_):
            try:
                self.store.reserve("concurrent", "app", 4)
                return True
            except BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            values = list(pool.map(reserve, range(30)))
        self.assertEqual(sum(values), 4)
        self.assertEqual(sum(x["calls"] for x in self.store.usage()), 4)

    def test_monthly_budget(self):
        self.store.reserve("monthly", "t", 100, 1)
        with self.assertRaises(BudgetExceeded):
            self.store.reserve("monthly", "t", 100, 1)

    def test_results_not_local_urls(self):
        from aicore.search import _hits
        r = _hits("tavily", [{"url": "http://127.0.0.1/secret"},
                            {"url": "file:///etc/passwd"},
                            {"url": "https://example.org/"}])
        self.assertEqual(len(r), 1)

    def test_deep_deduplicates_across_providers(self):
        fake = FakeTransport()
        result = SearchRouter(self.cfg, self.store, fake).search({"query": "deep", "mode": "deep"})
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(result["hits"]), 1)


if __name__ == "__main__":
    unittest.main()
