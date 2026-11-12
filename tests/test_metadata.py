import unittest
from aicore.metadata import ReferenceCatalog, normalize_reference
from aicore.store import Store


class FakeTransport:
    def __init__(self):
        self.calls = []
    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return {"deepseek": {"models": {
            "deepseek-chat": {"name": "DeepSeek Chat", "cost": {"input": .2, "output": .8},
                              "limit": {"context": 64000}, "reasoning": False,
                              "tool_call": True}}}}


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.fake = FakeTransport()
        self.catalog = ReferenceCatalog(self.store, self.fake)
    def tearDown(self):
        self.store.close()

    def test_reference_is_not_vendor_auth(self):
        result = self.catalog.list("deepseek")
        model = result["models"][0]
        self.assertFalse(result["billing_authoritative"])
        self.assertFalse(model["account_entitlement_verified"])
        self.assertEqual(model["cost_usd_per_million_tokens"]["input"], 0.2)

    def test_reference_cache(self):
        self.catalog.list("deepseek")
        self.catalog.list("deepseek")
        self.assertEqual(len(self.fake.calls), 1)

    def test_unknown_provider(self):
        with self.assertRaises(Exception):
            normalize_reference("unknown", {})

    def test_missing_reference_provider(self):
        result = normalize_reference("anthropic", {})
        self.assertEqual(result["models"], [])


if __name__ == "__main__":
    unittest.main()
