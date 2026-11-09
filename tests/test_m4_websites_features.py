"""M4b: website feature-first implementation retains modules, contracts and CLI."""
import importlib
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import architecture, paths


MODULES = (
    "ai_designer", "assets", "browser_validation", "builder", "design_kit",
    "feedback", "image_studio", "preview", "quality", "revision",
    "revision_context", "structured_builder",
)
ROOT_ALIASES = {
    "agentforge.product_builder": "builder",
    "agentforge.product_quality": "quality",
    "agentforge.product_revision": "revision",
    "agentforge.web_assets": "assets",
    "agentforge.web_design_kit": "design_kit",
    "agentforge.browser_validation": "browser_validation",
    "agentforge.image_studio_v24": "image_studio",
}


class WebsiteFeatureMigrationTests(unittest.TestCase):
    def test_canonical_domain_compatibility_module_identity(self):
        for name in MODULES:
            with self.subTest(module=name):
                canonical = importlib.import_module("agentforge.features.websites." + name)
                legacy = importlib.import_module("agentforge.domains.websites." + name)
                self.assertIs(canonical, legacy)
                self.assertIn("/features/websites/", canonical.__file__.replace("\\", "/"))

    def test_root_legacy_imports_keep_identity(self):
        for legacy_name, module in ROOT_ALIASES.items():
            with self.subTest(module=module):
                self.assertIs(importlib.import_module(legacy_name),
                              importlib.import_module("agentforge.features.websites." + module))
        for key in ("agentforge.website_preview", "agentforge.website_feedback"):
            self.assertTrue(architecture.LEGACY_IMPORTS[key].startswith(
                "agentforge.features.websites."))

    def test_workspace_and_proposal_paths_are_unchanged(self):
        builder = importlib.import_module("agentforge.features.websites.builder")
        self.assertEqual(paths.REPOSITORY_ROOT, builder.ROOT)
        self.assertEqual(paths.WORKSPACE_DIR, builder.WORKSPACE)
        self.assertEqual(paths.PRODUCTS_DIR, builder.PRODUCTS)
        self.assertEqual(paths.COMPANY_DATA_DIR / "product_builder" / "proposals",
                         builder.PROPOSALS)
        self.assertEqual("agentforge/features/websites", architecture.LAYOUT["website_domain"])

    def test_legacy_patching_is_visible_to_feature(self):
        feature = importlib.import_module("agentforge.features.websites.builder")
        old = importlib.import_module("agentforge.product_builder")
        with patch.object(old, "PRODUCTS", Path("example-products")):
            self.assertEqual(Path("example-products"), feature.PRODUCTS)

    def test_internal_website_imports_are_feature_owned(self):
        root = paths.REPOSITORY_ROOT / "agentforge" / "features" / "websites"
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("agentforge.domains.websites.", source)

    def test_legacy_cli_help_is_preserved_without_creating_artifacts(self):
        for name in ("assets", "browser_validation", "builder", "revision"):
            with self.subTest(name=name):
                cmd = [sys.executable, "-m", "agentforge.domains.websites." + name, "--help"]
                outcome = subprocess.run(cmd, cwd=paths.REPOSITORY_ROOT,
                                         capture_output=True, text=True, timeout=20)
                self.assertEqual(0, outcome.returncode, outcome.stderr)
                self.assertIn("usage:", outcome.stdout.lower())


if __name__ == "__main__":
    unittest.main()
