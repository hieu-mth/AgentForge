"""M4a: Growth implementation is feature-owned; old imports remain identical objects."""
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import architecture, paths


class GrowthFeatureMigrationTests(unittest.TestCase):
    def test_compatibility_modules_share_identity_and_callable(self):
        for name in ("store", "reports", "bundle"):
            with self.subTest(module=name):
                feature = importlib.import_module("agentforge.features.growth." + name)
                domain = importlib.import_module("agentforge.domains.growth." + name)
                legacy = importlib.import_module("agentforge.growth_" + name)
                self.assertIs(feature, domain)
                self.assertIs(domain, legacy)
                self.assertIn("/features/growth/", feature.__file__.replace("\\", "/"))

    def test_persistent_paths_and_architecture_contract_unchanged(self):
        store = importlib.import_module("agentforge.features.growth.store")
        self.assertEqual(paths.COMPANY_DATA_DIR / "s5_growth.sqlite3", store.DB)
        self.assertEqual(paths.REPOSITORY_ROOT, store.ROOT)
        self.assertEqual("agentforge/features/growth", architecture.LAYOUT["growth_feature"])
        for key in ("store", "reports", "bundle"):
            self.assertEqual("agentforge.features.growth." + key,
                             architecture.BUSINESS_DOMAIN_IMPORTS["agentforge.growth_" + key])

    def test_patch_legacy_module_updates_feature(self):
        feature = importlib.import_module("agentforge.features.growth.store")
        old = importlib.import_module("agentforge.growth_store")
        with patch.object(old, "DB", Path("custom-ledger.sqlite")):
            self.assertEqual(Path("custom-ledger.sqlite"), feature.DB)
        self.assertEqual(paths.COMPANY_DATA_DIR / "s5_growth.sqlite3", feature.DB)

    def test_no_legacy_domain_imports_inside_new_growth_modules(self):
        root = paths.REPOSITORY_ROOT / "agentforge" / "features" / "growth"
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("agentforge.domains.growth", source)
            self.assertNotIn("from agentforge import growth_store", source)
            self.assertNotIn("from agentforge.growth_bundle", source)


if __name__ == "__main__":
    unittest.main()
