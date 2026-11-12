"""No-key local model selection and zero-price keyed route budget regression."""
import os
import unittest
from unittest.mock import patch

from aicore.errors import BudgetExceeded, ProviderUnavailable
from aicore.free import choose_free_model, free_catalog, local_is_unmetered
from aicore.llm import ChatGateway
from aicore.models import ModelCatalog
from aicore.store import Store


class FreeTransport:
    def __init__(self, ollama=True, lmstudio=False):
        self.ollama, self.lmstudio = ollama, lmstudio
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen3:0.6b"}, {"name": "gpt-oss:cloud"}]} if self.ollama else {"models": []}
        if url.endswith("1234/v1/models"):
            return {"data": [{"id": "local-model"}]} if self.lmstudio else {"data": []}
        if url.endswith("/api/chat"):
            return {"message": {"content": "From local model"}, "prompt_eval_count": 3, "eval_count": 4}
        if "/chat/completions" in url:
            return {"choices": [{"message": {"content": "Free response"}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 5}}
        raise AssertionError("Unexpected request " + url)


class FreeModelTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.messages = [{"role": "user", "content": "hello"}]

    def tearDown(self):
        self.store.close()

    def test_auto_calls_local_model_without_paid_budget_or_api_key(self):
        transport = FreeTransport()
        gateway = ChatGateway(self.store, transport, daily_limit=0)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "", "OLLAMA_API_KEY": ""}):
            result = gateway.chat({"messages": self.messages})
        self.assertEqual(result["provider"], "ollama-local")
        self.assertEqual(result["model"], "qwen3:0.6b")
        self.assertEqual(result["choices"][0]["message"]["content"], "From local model")
        self.assertEqual(self.store.llm_usage()[0]["calls"], 1)

    def test_auto_discovers_lmstudio_if_ollama_unavailable(self):
        transport = FreeTransport(ollama=False, lmstudio=True)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            self.assertEqual(choose_free_model(transport), ("lm-studio-local", "local-model"))
        gateway = ChatGateway(self.store, transport, daily_limit=0)
        result = gateway.chat({"messages": self.messages})
        self.assertEqual(result["provider"], "lm-studio-local")

    def test_missing_runtime_fails_closed_not_missing_api_key(self):
        transport = FreeTransport(ollama=False)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            with self.assertRaises(ProviderUnavailable) as captured:
                ChatGateway(self.store, transport, daily_limit=0).chat({"messages": self.messages})
        self.assertIn("No ready keyless model", str(captured.exception))

    def test_keyed_zero_price_openrouter_fallback_separate_quota(self):
        transport = FreeTransport(ollama=False)
        gateway = ChatGateway(self.store, transport, daily_limit=0, free_cloud_daily_limit=1)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            result = gateway.chat({"messages": self.messages})
            self.assertEqual(result["provider"], "openrouter")
            self.assertEqual(result["model"], "openrouter/free")
            with self.assertRaises(BudgetExceeded):
                gateway.chat({"messages": self.messages})

    def test_paid_cloud_cannot_bypass_zero_budget(self):
        transport = FreeTransport()
        gateway = ChatGateway(self.store, transport, daily_limit=0)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with self.assertRaises(BudgetExceeded):
                gateway.chat({"provider": "openrouter", "model": "some-paid-model",
                              "messages": self.messages})

    def test_local_cloud_proxy_does_not_bypass_paid_budget(self):
        self.assertFalse(local_is_unmetered("ollama-local", "gpt-oss:cloud"))
        with self.assertRaises(BudgetExceeded):
            ChatGateway(self.store, FreeTransport(), daily_limit=0).chat({
                "provider": "ollama-local", "model": "gpt-oss:cloud", "messages": self.messages})

    def test_free_catalog_reports_actual_local_readiness(self):
        data = free_catalog(FreeTransport())
        self.assertTrue(data["local"][0]["engine_ready"])
        self.assertFalse(data["local"][1]["engine_ready"])
        self.assertTrue(all(m["requires_api_key"] for m in data["cloud"]))

    def test_auto_model_catalog_is_not_a_fabricated_cloud_listing(self):
        data = ModelCatalog(self.store, FreeTransport()).list("auto")
        self.assertEqual(data["source"], "local_discovery")
        self.assertEqual(data["models"][0]["provider"], "ollama-local")
        self.assertNotIn("gpt-oss:cloud", [m["id"] for m in data["models"]])


if __name__ == "__main__":
    unittest.main()
