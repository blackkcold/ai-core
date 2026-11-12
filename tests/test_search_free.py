"""Offline contract fixtures for public, zero-key specialist search APIs."""
import gzip
import io
import unittest
from dataclasses import replace
from unittest.mock import patch

from aicore.errors import ProviderUnavailable
from aicore.search import SearchRouter, SearchQuery
from aicore.search_free import PUBLIC_SEARCH, search_public
from aicore.settings import Settings
from aicore.store import Store
from aicore.transport import Transport


class PublicFixtureTransport:
    def __init__(self):
        self.requests = []

    def request_json(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if "wikipedia.org" in url:
            return {"query": {"search": [{"pageid": 12345, "title": "Python",
                                          "snippet": "<b>Programming</b> language"}]}}
        if "hn.algolia.com" in url:
            return {"hits": [{"objectID": "98", "title": "Technology",
                              "created_at": "2026-11-10T00:00:00Z"}]}
        if "api.openalex.org" in url:
            return {"results": [{"doi": "https://doi.org/10.1000/example",
                                 "display_name": "Research", "publication_date": "2026-10-01"}]}
        if "api.crossref.org" in url:
            return {"message": {"items": [{"URL": "https://doi.org/10.1000/abc",
                                          "title": ["Article"], "issued": {"date-parts": [[2026, 2, 3]]}}]}}
        if "europepmc" in url:
            return {"resultList": {"result": [{"id": "123", "source": "MED",
                                               "title": "Clinical Study",
                                               "firstPublicationDate": "2026-11-01"}]}}
        if "api.stackexchange.com" in url:
            return {"items": [{"link": "https://stackoverflow.com/questions/12/a",
                               "title": "Answer", "score": 10, "creation_date": 1780000000}]}
        if "openlibrary.org" in url:
            return {"docs": [{"key": "/works/OL123W", "title": "Book",
                              "author_name": ["Writer"], "first_publish_year": 2020}]}
        raise AssertionError("Unexpected URL: " + url)


class PublicSearchTests(unittest.TestCase):
    def setUp(self):
        self.transport = PublicFixtureTransport()
        self.store = Store()

    def tearDown(self):
        self.store.close()

    def test_seven_public_source_response_contracts(self):
        self.assertEqual(len(PUBLIC_SEARCH), 8)
        for name, info in PUBLIC_SEARCH.items():
            with self.subTest(provider=name):
                if name == "you-free-mcp":  # covered by separate MCP transport fixture
                    continue
                q = SearchQuery(query="test", provider=name)
                rows = search_public(name, q, self.transport, 20)
                self.assertTrue(rows)
                self.assertTrue(rows[0]["url"].startswith("https://"))
                self.assertTrue(rows[0]["title"])
                self.assertTrue(info["docs"].startswith("https://"))

    def test_default_general_search_needs_no_key(self):
        settings = replace(Settings(), search_enabled=("wikipedia",))
        result = SearchRouter(settings, self.store, self.transport).search({"query": "Python"})
        self.assertEqual(result["providers"], ["wikipedia"])
        self.assertEqual(result["hits"][0]["url"], "https://en.wikipedia.org/?curid=12345")
        self.assertEqual(result["attempts"], 1)

    def test_category_routes_to_specific_corpus(self):
        cfg = replace(Settings(), search_enabled=("wikipedia", "hackernews",
            "openalex", "crossref", "europepmc", "stackoverflow", "openlibrary"))
        router = SearchRouter(cfg, self.store, self.transport)
        self.assertEqual(router.search({"query": "startup", "category": "news"})["providers"],
                         ["hackernews"])
        self.assertEqual(router.search({"query": "gene", "category": "research"})["providers"],
                         ["openalex"])
        self.assertEqual(router.search({"query": "novel", "category": "books"})["providers"],
                         ["openlibrary"])

    def test_selected_provider_overrides_category(self):
        router = SearchRouter(Settings(), self.store, self.transport)
        result = router.search({"query": "Python", "provider": "stackoverflow"})
        self.assertEqual(result["providers"], ["stackoverflow"])

    def test_unsupported_recency_not_misrepresented(self):
        router = SearchRouter(Settings(), self.store, self.transport)
        with self.assertRaises(ProviderUnavailable):
            router.search({"query": "Python", "provider": "wikipedia", "recency": "7d"})
        self.assertFalse(self.transport.requests)

    def test_filters_pass_for_scoped_sources(self):
        search_public("hackernews", SearchQuery(query="news", recency="7d"),
                      self.transport, 20)
        self.assertIn("numericFilters=", self.transport.requests[-1][1])
        search_public("crossref", SearchQuery(query="papers", recency="30d"),
                      self.transport, 20)
        self.assertIn("from-pub-date", self.transport.requests[-1][1])

    def test_region_and_language_handling(self):
        search_public("wikipedia", SearchQuery(query="testing", language="zh-CN"),
                      self.transport, 20)
        self.assertIn("zh.wikipedia.org", self.transport.requests[-1][1])

    def test_transport_accepts_bounded_gzip(self):
        data = gzip.compress(b'{"items":[]}')
        class Response(io.BytesIO):
            headers = {"Content-Encoding": "gzip"}
        transport = Transport()
        transport.open = lambda *args, **kwargs: Response(data)
        response = transport.request_json("GET", "https://api.stackexchange.com/2.3/search")
        self.assertEqual(response, {"items": []})


if __name__ == "__main__":
    unittest.main()
