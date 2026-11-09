"""M5: all retained imports point directly at tested canonical features."""
import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import paths


ROOT = paths.REPOSITORY_ROOT
SCRIPT = ROOT / "scripts" / "compat_audit.py"
spec = importlib.util.spec_from_file_location("agentforge_compat_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

FACADES = {
    "webapp_architect": "propose",
    "webapp_reviewer": "review",
    "webapp_static_qa": "audit",
    "website_preview": "from_proposal",
    "website_feedback": "request_revision",
}


class M5CompatibilityTests(unittest.TestCase):
    def test_existing_public_aliases_are_all_present_and_feature_direct(self):
        result = audit.report()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["aliases_checked"], 22)
        self.assertEqual(result["aliases_removed"], 0)
        self.assertTrue(result["external_callers_unverified"])
        self.assertFalse(result["owner_data_modified"])
        self.assertTrue(all(row["source_ok"] for row in result["aliases"]))
        self.assertTrue(all(not row["safe_to_delete"] for row in result["aliases"]))

    def test_public_module_object_or_facade_callable_identity(self):
        for alias, canonical in audit.TARGETS.items():
            with self.subTest(alias=alias):
                old = importlib.import_module("agentforge." + alias)
                feature = importlib.import_module(canonical)
                if alias in FACADES:
                    fn = FACADES[alias]
                    self.assertIs(getattr(old, fn), getattr(feature, fn))
                else:
                    self.assertIs(old, feature)

    def test_static_callers_block_destructive_shortcuts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "agentforge").mkdir()
            (root / "tests").mkdir()
            alias = root / "agentforge/product_builder.py"
            alias.write_text(
                "import sys\nfrom agentforge.features.websites import builder as impl\n"
                "sys.modules[__name__] = impl\n", encoding="utf-8")
            (root / "tests/test_consumer.py").write_text(
                "from agentforge import product_builder\n", encoding="utf-8")
            result = audit.report(root=root, targets={
                "product_builder": "agentforge.features.websites.builder"})
            self.assertEqual(result["status"], "PASS")
            self.assertIn("tests/test_consumer.py",
                          result["aliases"][0]["internal_references"])
            self.assertFalse(result["aliases"][0]["safe_to_delete"])
            alias.write_text(
                "import sys\nfrom agentforge.domains.websites import builder as impl\n"
                "sys.modules[__name__] = impl\n", encoding="utf-8")
            self.assertEqual(audit.report(root=root, targets={
                "product_builder": "agentforge.features.websites.builder"})["status"], "FAIL")

    def test_do_not_read_user_data_or_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "agentforge").mkdir()
            data = root / "data/customer-private.py"
            data.parent.mkdir()
            data.write_text("API_KEY = 'never'\n", encoding="utf-8")
            out = audit.report(root=root, targets={
                "product_builder": "agentforge.features.websites.builder"})
            self.assertEqual(out["status"], "FAIL")
            self.assertNotIn("customer-private", str(out))
            self.assertEqual(data.read_text(encoding="utf-8"), "API_KEY = 'never'\n")


if __name__ == "__main__":
    unittest.main()
