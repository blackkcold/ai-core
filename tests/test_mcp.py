import unittest
from aicore.mcp import MCPServer
from aicore.service import Service
from aicore.settings import Settings
from aicore.store import Store


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.mcp = MCPServer(Service(Settings(), store=self.store,
                         fetcher=lambda url: {"url": url, "text": "sample"}))
    def tearDown(self):
        self.store.close()

    def call(self, method, params=None):
        return self.mcp.handle({"jsonrpc": "2.0", "id": 10, "method": method,
                                "params": params or {}})

    def test_initialize(self):
        result = self.call("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])

    def test_tool_catalog(self):
        names = [x["name"] for x in self.call("tools/list")["result"]["tools"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"web_search", "web_fetch", "list_models", "chat", "generate_setup"} <= set(names))

    def test_notification_no_reply(self):
        self.assertIsNone(self.mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_fetch(self):
        result = self.call("tools/call", {"name": "web_fetch",
                   "arguments": {"url": "https://example.org/"}})["result"]
        self.assertEqual(result["structuredContent"]["text"], "sample")

    def test_bad_tool_is_error_result(self):
        result = self.call("tools/call", {"name": "unknown", "arguments": {}})["result"]
        self.assertTrue(result["isError"])

    def test_missing_method(self):
        self.assertEqual(self.call("unknown")["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
