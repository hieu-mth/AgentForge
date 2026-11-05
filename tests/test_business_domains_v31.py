"""V3.1 canonical website/media/growth domains and legacy module aliases."""
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch
from agentforge import architecture, paths

class BusinessDomainTests(unittest.TestCase):
    def test_same_module_identity_for_business_domains(self):
        self.assertEqual(14, len(architecture.BUSINESS_DOMAIN_IMPORTS))
        for legacy, canonical in architecture.BUSINESS_DOMAIN_IMPORTS.items():
            with self.subTest(legacy=legacy):
                self.assertIs(importlib.import_module(legacy),
                              importlib.import_module(canonical))

    def test_persistent_roots_unmodified(self):
        from agentforge import product_builder as builder
        from agentforge import media_assets, growth_store
        self.assertEqual(paths.REPOSITORY_ROOT, builder.ROOT)
        self.assertEqual(paths.WORKSPACE_DIR, builder.WORKSPACE)
        self.assertEqual(paths.PRODUCTS_DIR, builder.PRODUCTS)
        self.assertEqual(paths.COMPANY_DATA_DIR / "product_builder" / "proposals",
                         builder.PROPOSALS)
        self.assertEqual(paths.REPOSITORY_ROOT, media_assets.ROOT)
        self.assertEqual(paths.WORKSPACE_DIR / "media", media_assets.OUTPUTS)
        self.assertEqual(paths.COMPANY_DATA_DIR / "s5_growth.sqlite3", growth_store.DB)

    def test_old_module_patch_changes_canonical_module(self):
        from agentforge import product_builder, growth_store
        import agentforge.domains.websites.builder as canonical_builder
        import agentforge.domains.growth.store as canonical_growth
        with patch.object(product_builder, "PRODUCTS", Path("test-products")):
            self.assertEqual(Path("test-products"), canonical_builder.PRODUCTS)
        with patch.object(growth_store, "DB", Path("test-ledger.sqlite")):
            self.assertEqual(Path("test-ledger.sqlite"), canonical_growth.DB)

    def test_business_domain_source_does_not_move_storage_roots(self):
        for name in architecture.BUSINESS_DOMAIN_IMPORTS.values():
            module = importlib.import_module(name)
            code = Path(module.__file__).read_text(encoding="utf-8-sig")
            self.assertNotIn("ROOT = Path(__file__).resolve().parents[2]", code)

if __name__ == "__main__":
    unittest.main()
