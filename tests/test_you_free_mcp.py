"""Offline MCP transport contract for You.com's officially keyless web search."""
import io
import json
import unittest

from aicore.errors import InvalidRequest, ProviderUnavailable
from aicore.search import SearchQuery, SearchRouter
from aicore.search_free import search_public
from aicore.settings import Settings
from aicore.store import Store


class MCPResponse(io.BytesIO):
    def __init__(self, content, content_type):
        super().__init__(content)
        self.headers = {"Content-Type": content_type}


class FakeMCPTransport:
    def __init__(self, event_mode=False, failure=None):
        self.calls = []
        self.event_mode = event_mode
        self.failure = failure

    def open(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        reply = {"jsonrpc": "2.0", "id": 1, "result": {
            "resultType": "complete", "structuredContent": {
                "results": {"web": [{"url": "https://example.com/current",
                    "title": "Current update",
                    "contents": {"highlights": ["evidence"]},
                    "page_age": "2026-11-12T01:02:03Z"}]}}}}
        if self.failure == "rpc":
            reply = {"jsonrpc": "2.0", "id": 1,
                     "error": {"code": -32602, "message": "unsupported"}}
        if self.failure == "tool":
            reply = {"jsonrpc": "2.0", "id": 1,
                     "result": {"isError": True, "content": [{"type": "text", "text": "limit"}]}}
        if self.failure == "id":
            reply["id"] = 999
        if self.event_mode:
            stream = ("data: " + json.dumps({"jsonrpc": "2.0", "method": "notifications/message"}) +
                      "\n\n" + "data: " + json.dumps(reply) + "\n\n")
            return MCPResponse(stream.encode(), "text/event-stream")
        return MCPResponse(json.dumps(reply).encode(), "application/json")


class YouFreeMCPTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()

    def tearDown(self):
        self.store.close()

    def test_json_and_sse_responses(self):
        for mode in [False, True]:
            transport = FakeMCPTransport(event_mode=mode)
            hits = search_public("you-free-mcp", SearchQuery(query="What's new?", limit=5),
                                 transport, 20)
            self.assertEqual(hits[0]["title"], "Current update")
            self.assertEqual(hits[0]["snippet"], "evidence")
            method, url, opts = transport.calls[0]
            self.assertEqual(method, "POST")
            self.assertEqual(url, "https://api.you.com/mcp?profile=free")
            self.assertEqual(opts["headers"]["MCP-Protocol-Version"], "2026-07-28")
            self.assertNotIn("Authorization", opts["headers"])
            self.assertEqual(opts["body"]["params"]["name"], "you-search")
            self.assertEqual(opts["body"]["params"]["_meta"]
                             ["io.modelcontextprotocol/protocolVersion"], "2026-07-28")

    def test_errors_and_unmatched_rpc_id(self):
        for failure in ["rpc", "tool", "id"]:
            with self.subTest(failure=failure):
                with self.assertRaises(ProviderUnavailable):
                    search_public("you-free-mcp", SearchQuery(query="test"),
                                  FakeMCPTransport(failure=failure), 20)

    def test_no_invented_90day_filter(self):
        transport = FakeMCPTransport()
        with self.assertRaises(InvalidRequest):
            search_public("you-free-mcp", SearchQuery(query="test", recency="90d"),
                          transport, 20)
        self.assertEqual(transport.calls, [])

    def test_default_general_search_is_keyless_web(self):
        fake = FakeMCPTransport()
        result = SearchRouter(Settings(), self.store, fake).search({"query": "test"})
        self.assertEqual(result["providers"], ["you-free-mcp"])
        self.assertEqual(result["hits"][0]["url"], "https://example.com/current")

    def test_search_count_and_language_override(self):
        fake = FakeMCPTransport()
        search_public("you-free-mcp", SearchQuery(query="hi", limit=4,
                      language="zh-CN", recency="7d"), fake, 20)
        body = fake.calls[0][2]["body"]
        self.assertEqual(body["params"]["arguments"]["freshness"], "week")
        self.assertEqual(body["params"]["_meta"]["com.you.com/search"]["language"], "ZH")


if __name__ == "__main__":
    unittest.main()
