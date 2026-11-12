import os
import unittest
from unittest.mock import patch
from aicore.models import ModelCatalog
from aicore.store import Store


class FakeTransport:
    def __init__(self):
        self.calls = []
    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if "/api/tags" in url:
            return {"models": [{"name": "llama3.2:latest"}]}
        if "generativelanguage" in url:
            return {"models": [{"name": "models/gemini-2.5-flash",
                                "supportedGenerationMethods": ["generateContent"]}]}
        return {"data": [{"id": "deepseek-chat", "object": "model"}]}


class ModelsTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.transport = FakeTransport()
        self.catalog = ModelCatalog(self.store, self.transport)

    def tearDown(self):
        self.store.close()

    def test_official_api_and_cache(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake"}):
            result = self.catalog.list("deepseek")
            cached = self.catalog.list("deepseek")
        self.assertEqual(result["source"], "provider_api")
        self.assertEqual(result["models"][0]["id"], "deepseek-chat")
        self.assertEqual(cached["source"], "cached_provider_api")
        self.assertEqual(len(self.transport.calls), 1)

    def test_missing_credential(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            result = self.catalog.list("deepseek")
        self.assertEqual(result["source"], "credentials_required")
        self.assertFalse(result["models"])

    def test_manual_models_are_not_invented(self):
        self.assertEqual(self.catalog.list("glm")["source"], "manual_required")

    def test_ollama_local(self):
        result = self.catalog.list("ollama-local")
        self.assertEqual(result["models"][0]["id"], "llama3.2:latest")

    def test_gemini_model_prefix(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake"}):
            result = self.catalog.list("gemini")
        self.assertEqual(result["models"][0]["id"], "gemini-2.5-flash")
        self.assertTrue(result["models"][0]["capabilities_verified"])


if __name__ == "__main__":
    unittest.main()
