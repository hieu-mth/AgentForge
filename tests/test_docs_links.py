"""Documentation link checker regressions: prevent dead links in main README."""
import tempfile
import unittest
from pathlib import Path

from scripts.check_docs import ROOT, broken_links


class DocsLinksTests(unittest.TestCase):
    def test_tracked_repository_docs_resolve(self):
        self.assertEqual([], broken_links(ROOT))

    def test_missing_and_escaping_relative_links_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "README.md").write_text("# Home\n", encoding="utf-8")
            (root / "docs" / "valid.md").write_text("# Existing\n", encoding="utf-8")
            (root / "docs" / "README.md").write_text(
                "[Home](../README.md) [Valid](valid.md#anchor)\n"
                "[Remote](https://example.org/path) [Anchor](#section)\n"
                "[Missing](gone.md) [Escape](../../private.md)\n",
                encoding="utf-8",
            )
            found = broken_links(root)
            self.assertEqual(2, len(found))
            self.assertEqual(["gone.md", "../../private.md"],
                             [item[2] for item in found])

    def test_ignores_local_user_data_and_vendor_node_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "README.md").write_text(
                "[Root](../README.md)", encoding="utf-8")
            (root / "README.md").write_text("# AgentForge", encoding="utf-8")
            for dirname in ("node_modules", "workspace", "data", ".venv"):
                folder = root / "ui" / dirname
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "README.md").write_text(
                    "[Broken](missing.md)", encoding="utf-8")
            self.assertEqual([], broken_links(root))


if __name__ == "__main__":
    unittest.main()
