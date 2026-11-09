"""Architecture catalog must track every Python module in current checkout."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "architecture" / "FILE_CATALOG.md"


class ArchitectureFileCatalogTests(unittest.TestCase):
    def test_every_current_python_module_has_inventory_entry(self):
        inventory = CATALOG.read_text(encoding="utf-8")
        source = ROOT / "agentforge"
        self.assertTrue(source.is_dir(), "This test targets the root-level Python package")
        modules = sorted(source.rglob("*.py"))
        self.assertGreaterEqual(len(modules), 100)
        for module in modules:
            rel = module.relative_to(source).as_posix()
            with self.subTest(module=rel):
                self.assertIn(f"`{rel}`", inventory)

    def test_current_docs_explicitly_distinguish_approved_target_from_runtime(self):
        target = (ROOT / "docs" / "architecture" / "TARGET_STRUCTURE.md").read_text(encoding="utf-8")
        runtime = (ROOT / "docs" / "architecture" / "REPOSITORY_STRUCTURE.md").read_text(encoding="utf-8")
        self.assertIn("M4 research/ops PENDING", target)
        self.assertIn("M5 phase 2 PENDING", target)
        self.assertIn("CURRENT IMPLEMENTATION", runtime)
        self.assertIn("agentforge/", runtime)
        self.assertIn("dashboard/", target)


if __name__ == "__main__":
    unittest.main()
