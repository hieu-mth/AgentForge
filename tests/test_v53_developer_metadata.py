"""V5.3: long display labels cannot invalidate valid React source proposals.

Fixture only: no provider calls, JS execution, or host workspace writes.
"""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import model, skill_runner, webapp_developer as developer
from tests.test_webapp_developer_v42b import MODEL


class DeveloperMetadataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name, value in (
            ("PROPOSALS", root / "proposals"),
            ("PROJECTS", root / "projects"),
        ):
            guard = patch.object(developer, name, value)
            guard.start()
            self.addCleanup(guard.stop)

    def test_schema_prompts_short_title_and_summary(self):
        self.assertEqual(
            developer.CODE_SCHEMA["properties"]["title"]["maxLength"], 100)
        self.assertEqual(
            developer.CODE_SCHEMA["properties"]["summary"]["maxLength"], 240)
        self.assertEqual(
            developer.CODE_SCHEMA["properties"]["title"]["minLength"], 1)

    def test_overlong_metadata_truncates_safely_not_source(self):
        candidate = deepcopy(MODEL)
        candidate["title"] = "Ứng dụng thương mại điện tử demo " * 8
        candidate["summary"] = (
            "Ứng dụng có tìm kiếm, danh mục, giỏ hàng, hiển thị sản phẩm "
            "và tương tác trong bộ nhớ React. " * 8)
        with patch.object(model, "generate_json", return_value=candidate) as inference:
            receipt = developer.propose(
                "metadata-shop", "Tạo app local gồm danh mục và giỏ hàng giả lập.")
        inference.assert_called_once()
        prompt = inference.call_args.args[0]
        self.assertIn("at most 100 characters", prompt)
        self.assertIn("at most 240 characters", prompt)

        document, _ = developer._read_proposal(receipt["proposal_id"])
        self.assertTrue(0 < len(document["title"]) <= 100)
        self.assertTrue(0 < len(document["summary"]) <= 240)
        self.assertTrue(candidate["title"].startswith(document["title"]))
        self.assertTrue(candidate["summary"].startswith(document["summary"]))
        sources = {item["path"]: item["content"] for item in document["files"]}
        self.assertEqual(sources["src/App.jsx"], MODEL["files"][0]["content"])
        self.assertEqual(sources["src/styles.css"], MODEL["files"][1]["content"])
        self.assertFalse(developer.PROJECTS.exists())
        self.assertFalse(document["execution_authorized"])

    def test_whitespace_is_canonical_without_changing_code(self):
        candidate = deepcopy(MODEL)
        candidate["title"] = "   Shop  \n   React \t Demo "
        candidate["summary"] = " Demo  \n  tìm kiếm \t và   giỏ hàng.  "
        result = developer.validate_code(candidate)
        self.assertEqual(result["title"], "Shop React Demo")
        self.assertEqual(result["summary"], "Demo tìm kiếm và giỏ hàng.")
        self.assertEqual(result["files"][0]["content"], MODEL["files"][0]["content"])

    def test_missing_or_nonstring_metadata_fails_with_named_redacted_error(self):
        for key in ("title", "summary"):
            for value in ("   \n   ", None, 120, []):
                with self.subTest(field=key, input_type=type(value).__name__):
                    candidate = deepcopy(MODEL)
                    candidate[key] = value
                    with patch.object(model, "generate_json", return_value=candidate) as inf:
                        with self.assertRaisesRegex(
                            ValueError, "APP_CODE_METADATA_INVALID: " + key
                        ) as failure:
                            developer.propose("metadata-shop", "Tạo app React demo.")
                        inf.assert_called_once()
                    safe = skill_runner._safe_failure("webapp.develop", failure.exception)
                    self.assertTrue(
                        safe.startswith("APP_CODE_" + key.upper() + "_INVALID:"),
                        safe)
        self.assertFalse(developer.PROPOSALS.exists())
        self.assertFalse(developer.PROJECTS.exists())

    def test_long_metadata_never_bypasses_source_safety(self):
        candidate = deepcopy(MODEL)
        candidate["title"] = "Mẫu tiêu đề demo " * 40
        candidate["summary"] = "Tóm tắt thử nghiệm " * 40
        candidate["files"][0]["content"] += "\nfetch('http://example.invalid');"
        with patch.object(model, "generate_json", return_value=candidate) as inf:
            with self.assertRaisesRegex(ValueError, "APP_CODE_UNSAFE"):
                developer.propose("unsafe-metadata", "Tạo web React thử nghiệm.")
            inf.assert_called_once()
        self.assertFalse(developer.PROPOSALS.exists())


if __name__ == "__main__":
    unittest.main()
