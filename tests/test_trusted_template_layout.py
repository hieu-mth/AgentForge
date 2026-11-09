"""The marketplace scaffold is a reviewed runtime dependency, not a disposable demo."""
import unittest

from agentforge.paths import REPOSITORY_ROOT
from agentforge.domains.webapps import builder, developer, toolchain


class TrustedTemplateLayoutTests(unittest.TestCase):
    def test_runtime_scaffold_is_in_templates_only(self):
        expected = REPOSITORY_ROOT / "templates" / "novamart"
        self.assertEqual(expected, builder.REFERENCE)
        self.assertEqual(expected, toolchain.REFERENCE)
        self.assertEqual(builder, developer.base)
        self.assertFalse((REPOSITORY_ROOT / "examples" / "novamart").exists())
        self.assertTrue((expected / "README.md").is_file())
        self.assertTrue((expected / "package-lock.json").is_file())
        for filename in builder.TEMPLATES:
            with self.subTest(filename=filename):
                self.assertTrue((expected / filename).is_file())

    def test_reviewed_toolchain_keeps_lockfile(self):
        generated = toolchain.project_files("runtime-template-test")
        self.assertEqual({"package.json", "package-lock.json"}, set(generated))
        self.assertIn("@agentforge/runtime-template-test", generated["package.json"])
        self.assertIn("@agentforge/runtime-template-test", generated["package-lock.json"])


if __name__ == "__main__":
    unittest.main()
