import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from aicore.generator import generate_setup
from aicore.registry import RegistryError, get_provider, list_providers
from aicore.settings import Settings


class RegistryTests(unittest.TestCase):
    def test_known_providers_and_urls(self):
        items = list_providers()
        self.assertGreaterEqual(len(items), 12)
        self.assertEqual(len({x.id for x in items}), len(items))
        for item in items:
            self.assertTrue(item.base_url.startswith("https://") or item.id == "ollama-local")

    def test_unknown_provider(self):
        with self.assertRaises(RegistryError):
            get_provider("not-a-provider")

    def test_model_discovery_not_invented(self):
        self.assertIsNone(get_provider("glm").models_url)
        self.assertEqual(get_provider("opencode-zen").protocol, "catalog-only")

    def test_python_sample_compiles(self):
        for name in ["deepseek", "anthropic", "ollama-local"]:
            snippet = generate_setup(name, language="python")
            compile(snippet["code"], "<sample>", "exec")
            self.assertNotIn("sk-", snippet["code"])

    def test_languages(self):
        for lang in ("typescript", "swift", "curl"):
            code = generate_setup("deepseek", language=lang, model="deepseek-chat")["code"]
            self.assertIn("deepseek-chat", code)

    def test_native_sample(self):
        item = generate_setup("anthropic", language="curl", mode="native", model="claude-test")
        self.assertIn("/messages", item["code"])
        self.assertIn("$ANTHROPIC_API_KEY", item["code"])

    def test_reject_injection_in_model(self):
        with self.assertRaises(Exception):
            generate_setup("deepseek", model="abc'; DROP TABLE --")

    def test_public_list_has_no_secret(self):
        item = get_provider("deepseek").public()
        self.assertEqual(item["key_env"], "DEEPSEEK_API_KEY")
        self.assertNotIn("api_key", item)

    def test_nonloopback_requires_token(self):
        with patch.dict(os.environ, {"AI_CORE_HOST": "0.0.0.0", "AI_CORE_TOKEN": "",
             "AI_CORE_PROJECT_TOKENS": "{}"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_short_token_rejected(self):
        with patch.dict(os.environ, {"AI_CORE_TOKEN": "short"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_project_token_isolation(self):
        data = '{"news":"012345678901234567890123","research":"abcdefghijklmnopqrstuvwx"}'
        with patch.dict(os.environ, {"AI_CORE_PROJECT_TOKENS": data}, clear=True):
            self.assertEqual(set(Settings.from_env().project_tokens), {"news", "research"})

    def test_invalid_origin_rejected(self):
        with patch.dict(os.environ, {"AI_CORE_ALLOWED_ORIGINS": "https://example.com/evil"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
