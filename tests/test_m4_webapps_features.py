"""M4c: Webapp canonical features retain root compatibility and execution gates."""
import importlib
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import architecture, paths


MODULES = ("architect", "builder", "developer", "reviewer", "sandbox", "static_qa",
           "syntax", "toolchain")


class WebappFeatureMigrationTests(unittest.TestCase):
    def test_legacy_domains_resolve_to_feature_module_objects(self):
        for name in MODULES:
            with self.subTest(module=name):
                feature = importlib.import_module("agentforge.features.webapps." + name)
                legacy = importlib.import_module("agentforge.domains.webapps." + name)
                self.assertIs(feature, legacy)
                self.assertIn("/features/webapps/", feature.__file__.replace("\\", "/"))

    def test_public_root_aliases_and_facades_preserve_symbols(self):
        for legacy_name, new_name in {
            "agentforge.webapp_builder": "builder",
            "agentforge.webapp_developer": "developer",
            "agentforge.webapp_sandbox": "sandbox",
        }.items():
            with self.subTest(legacy=legacy_name):
                self.assertIs(importlib.import_module(legacy_name),
                              importlib.import_module("agentforge.features.webapps." + new_name))
        for old, new, fn in (
            ("agentforge.webapp_architect", "architect", "propose"),
            ("agentforge.webapp_reviewer", "reviewer", "review"),
            ("agentforge.webapp_static_qa", "static_qa", "audit"),
        ):
            with self.subTest(legacy=old):
                self.assertIs(getattr(importlib.import_module(old), fn),
                              getattr(importlib.import_module("agentforge.features.webapps." + new), fn))

    def test_workspace_and_template_paths_are_unchanged(self):
        builder = importlib.import_module("agentforge.features.webapps.builder")
        self.assertEqual(paths.REPOSITORY_ROOT, builder.ROOT)
        self.assertEqual(paths.REPOSITORY_ROOT / "templates" / "novamart", builder.REFERENCE)
        self.assertEqual(paths.WORKSPACE_DIR / "webapps", builder.PROJECTS)
        self.assertEqual(paths.COMPANY_DATA_DIR / "webapp_builder" / "proposals",
                         builder.PROPOSALS)
        self.assertEqual("agentforge/features/webapps", architecture.LAYOUT["webapp_feature"])

    def test_legacy_patching_changes_feature_module(self):
        canonical = importlib.import_module("agentforge.features.webapps.builder")
        old = importlib.import_module("agentforge.webapp_builder")
        with patch.object(old, "PROJECTS", Path("test-projects")):
            self.assertEqual(Path("test-projects"), canonical.PROJECTS)

    def test_internal_imports_have_no_old_domain_references(self):
        for path in (paths.REPOSITORY_ROOT / "agentforge" / "features" / "webapps").glob("*.py"):
            self.assertNotIn("agentforge.domains.webapps", path.read_text(encoding="utf-8"))

    def test_legacy_cli_help_does_not_run_generated_source(self):
        for name in ("builder", "developer", "sandbox"):
            with self.subTest(name=name):
                result = subprocess.run(
                    [sys.executable, "-m", "agentforge.domains.webapps." + name, "--help"],
                    cwd=paths.REPOSITORY_ROOT, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
