import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestDependencyManifest(unittest.TestCase):

    def test_lxml_is_direct_dependency(self):
        content = (
            ROOT / "pyproject.toml"
        ).read_text(encoding="utf-8-sig")

        config = tomllib.loads(content)
        dependencies = config["project"]["dependencies"]

        self.assertTrue(
            any(
                item.startswith("lxml==")
                for item in dependencies
            ),
            "lxml must be a direct project dependency",
        )


if __name__ == "__main__":
    unittest.main()
