"""Repository V2.8 architecture and backwards-compatibility contract tests."""
import importlib
import inspect
import re
import unittest
from pathlib import Path

from agentforge import architecture


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_explicit_python_domain_layout(self):
        root = architecture.REPOSITORY_ROOT
        self.assertTrue((root / "pyproject.toml").is_file())
        self.assertTrue((root / "ui" / "dashboard" / "package.json").is_file())
        for key in ("ai", "core", "website_domain", "storage"):
            package = root / architecture.LAYOUT[key]
            self.assertTrue((package / "__init__.py").is_file(), key)
        self.assertEqual({"data", "workspace"}, set(architecture.PERSISTENT_DIRS))
        self.assertFalse(architecture.snapshot()["data_cleanup_allowed"])
        self.assertFalse(architecture.snapshot()["workspace_cleanup_allowed"])

    def test_moved_implementations_preserve_legacy_callable_identity(self):
        for legacy, canonical in architecture.LEGACY_IMPORTS.items():
            with self.subTest(legacy=legacy):
                old = importlib.import_module(legacy)
                new = importlib.import_module(canonical)
                self.assertNotEqual(Path(old.__file__), Path(new.__file__))
                symbols = {
                    "agentforge.prompt_intake": "plan_request",
                    "agentforge.result_view": "present",
                    "agentforge.website_preview": "from_proposal",
                    "agentforge.website_feedback": "request_revision",
                    "agentforge.artifact_catalog": "report",
                    "agentforge.model_health": "check",
                }
                method = symbols[legacy]
                self.assertIs(getattr(old, method), getattr(new, method))
                self.assertEqual(inspect.signature(getattr(old, method)),
                                 inspect.signature(getattr(new, method)))

    def test_canonical_modules_are_not_filesystem_root_relative(self):
        for name in architecture.LEGACY_IMPORTS.values():
            module = importlib.import_module(name)
            body = Path(module.__file__).read_text(encoding="utf-8")
            # File-based root resolution from a moved module breaks on Windows.
            self.assertNotRegex(body, r"__file__\)\.resolve\(\)\.parents\[2\]")

    def test_runtime_and_frontend_build_data_are_gitignored(self):
        lines = (architecture.REPOSITORY_ROOT / ".gitignore").read_text(
            encoding="utf-8").splitlines()
        ignored = {line.strip() for line in lines}
        for rule in ("data/", "workspace/", "ui/dashboard/dist/",
                     "ui/dashboard/node_modules/"):
            self.assertIn(rule, ignored)

    def test_ui_does_not_embed_storage_operations(self):
        sources = architecture.REPOSITORY_ROOT / "ui" / "dashboard" / "src"
        for file in sources.rglob("*"):
            if file.suffix not in (".js", ".jsx", ".ts", ".tsx"):
                continue
            text = file.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"sqlite3\b|better-sqlite3|child_process|execSync")
        # UI code must always call authenticated same-origin Python API.
        api = (sources / "api.js").read_text(encoding="utf-8")
        self.assertIn("credentials:'same-origin'", api)
        self.assertIn("X-CSRF-Token", api)


if __name__ == "__main__":
    unittest.main()
