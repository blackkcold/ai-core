"""Static shipping contracts; prevents version, registry and docs drift."""
import json
import pathlib
import tomllib
import unittest

import aicore
from aicore.openapi import spec
from aicore.registry import list_providers
from aicore.search import list_search_providers
from aicore.settings import Settings

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_runtime_package_manifest_and_api_versions_agree(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
        self.assertEqual(project["project"]["version"], aicore.__version__)
        self.assertEqual(manifest["version"], aicore.__version__)
        self.assertEqual(spec()["info"]["version"], aicore.__version__)

    def test_registered_provider_counts_match_manifest(self):
        manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
        self.assertEqual(len(list_providers()), manifest["providers"]["model"])
        self.assertEqual(len(list_search_providers()), manifest["providers"]["search"])

    def test_keyless_search_defaults_and_safe_paid_limits(self):
        cfg = Settings()
        self.assertEqual(cfg.llm_daily_limit, 0)
        self.assertFalse(cfg.search_allow_metered)
        self.assertTrue(set(cfg.search_enabled).issubset(set(cfg.search_daily_limits)))
        self.assertIn("you-free-mcp", cfg.search_enabled)
        self.assertLessEqual(cfg.search_daily_limits["you-free-mcp"], 100)

    def test_bilingual_readmes_have_correct_release_and_license_badges(self):
        for name in ["README.md", "README.zh-CN.md"]:
            content = (ROOT / name).read_text()
            self.assertIn("github/v/release/blackkcold/ai-core", content)
            self.assertIn("License-MIT", content)
            self.assertIn("docker compose", content)
            self.assertIn("local-llm", content)
            self.assertNotIn("## Changelog", content)
            self.assertNotIn("## Release History", content)

    def test_protocol_and_clients_have_free_model_endpoint(self):
        self.assertIn("/v1/free/models", spec()["paths"])
        for name in ["aicore/client.py", "clients/typescript/client.ts",
                     "clients/swift/AICoreClient.swift",
                     "clients/kotlin/AICoreClient.kt"]:
            content = (ROOT / name).read_text()
            self.assertIn("/v1/free/models", content)

    def test_release_workflow_is_dynamic_not_hardcoded(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("chore(release): v", workflow)
        self.assertIn("gh release create", workflow)
        self.assertNotIn("gh release create v1.0.0", workflow)
        self.assertIn("kotlin:", workflow)
        self.assertIn("docker compose", workflow)


if __name__ == "__main__":
    unittest.main()
