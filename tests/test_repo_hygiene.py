"""Hygiene must never delete project data and must require a confirmation."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class RepositoryHygieneTests(unittest.TestCase):
    def test_readonly_and_scoped_confirmed_clean(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "repo_hygiene.py"
        spec = importlib.util.spec_from_file_location("af_repo_hygiene", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src" / "pkg" / "__pycache__"
            src.mkdir(parents=True)
            cache = src / "sample.pyc"
            cache.write_bytes(b"compiled")
            data = root / "data" / "business.sqlite3"
            data.parent.mkdir()
            data.write_bytes(b"never delete")
            with patch.object(module, "SCOPES", (root / "src", root / "tests")):
                info = module.report()
                self.assertEqual(1, info["pyc_files"])
                self.assertTrue(cache.exists())
                with self.assertRaises(PermissionError):
                    module.report(clean=True)
                self.assertTrue(cache.exists())
                cleaned = module.report(clean=True, confirm=True)
                self.assertEqual(1, cleaned["deleted"])
                self.assertFalse(cache.exists())
                self.assertTrue(data.exists())


if __name__ == "__main__":
    unittest.main()
