"""V4.0b security and happy-path marketplace application proposal regression."""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import webapp_builder as app

SPEC = {
    "brand": "NovaMart Việt",
    "headline": "Tìm những món đồ phù hợp",
    "tagline": "Trải nghiệm marketplace có lọc, tìm kiếm và giỏ hàng demo.",
    "accent": "#ed603b",
    "categories": [
        {"id": "electronics", "name": "Điện tử", "icon": "♫"},
        {"id": "home", "name": "Nhà cửa", "icon": "⌂"},
        {"id": "fashion", "name": "Thời trang", "icon": "◇"},
    ],
    "products": [
        {"id": "item" + str(i), "category": ["electronics", "home", "fashion"][i % 3],
         "name": "Sản phẩm minh họa số " + str(i), "price": 100000 + i * 15000,
         "description": "Sản phẩm giả lập để đánh giá giao diện.",
         "tone": "sand", "icon": "✦"}
        for i in range(8)
    ],
}
BRIEF = "Tạo website như Shopee nhưng mang thương hiệu NovaMart với tìm kiếm và giỏ hàng demo."


class WebappBuilderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for field, value in (
            ("PROJECTS", self.root / "workspace" / "webapps"),
            ("PROPOSALS", self.root / "data" / "company" / "webapp_builder" / "proposals"),
        ):
            p = patch.object(app, field, value)
            p.start()
            self.addCleanup(p.stop)

    def _propose(self, spec=None):
        with patch("agentforge.model.generate_json", return_value=SPEC if spec is None else spec) as model:
            result = app.propose("novamart-test", BRIEF)
            model.assert_called_once()
            self.assertEqual(model.call_args.kwargs, {"worker_id": "product_builder"})
            self.assertEqual(model.call_args.args[1], app.APP_SCHEMA)
        return result

    def test_model_returns_data_and_generates_functional_react_source_unexecuted(self):
        receipt = self._propose()
        self.assertFalse(app.PROJECTS.exists())
        document, path = app._read_proposal(receipt["proposal_id"])
        self.assertTrue(path.is_file())
        self.assertEqual(document["status"], "PROPOSED_NOT_APPLIED")
        self.assertEqual(document["sha256"], receipt["sha256"])
        self.assertFalse(document["execution_authorized"])
        self.assertFalse(document["spending_authorized"])
        self.assertFalse(document["deployment_authorized"])
        files = {entry["path"]: entry["content"] for entry in document["files"]}
        self.assertEqual(set(files), set(app.OUTPUTS))
        self.assertIn("import { CATEGORIES, PRODUCTS, SHOP }", files["src/App.jsx"])
        self.assertIn("cartTotals", files["src/App.jsx"])
        self.assertIn('NovaMart Việt', files["index.html"])
        self.assertIn('export const PRODUCTS', files["src/catalog.js"])
        self.assertIn("react", files["package.json"])
        self.assertIn("vite", files["package.json"])
        self.assertNotIn("http://example", files["src/catalog.js"])
        self.assertNotIn("child_process", files["src/catalog.js"])
        metadata = app.inspect(receipt["proposal_id"])
        self.assertEqual(metadata["sha256"], receipt["sha256"])
        self.assertIn("proposal_path", metadata)

    def test_source_data_is_encoded_without_model_js_css_or_external_code(self):
        attack = deepcopy(SPEC)
        attack["brand"] = '<svg onload=alert(1)>'
        attack["products"][0]["name"] = '</script><script>alert(1)</script>'
        attack["products"][0]["description"] = 'fetch("https://outside.invalid")'
        result = self._propose(attack)
        doc, _ = app._read_proposal(result["proposal_id"])
        files = {entry["path"]: entry["content"] for entry in doc["files"]}
        self.assertIn("&lt;svg", files["index.html"])
        self.assertIn("\\u003cscript", files["src/catalog.js"])
        self.assertNotIn("<script>alert", files["src/catalog.js"])
        self.assertNotIn("</script>", files["src/catalog.js"])
        self.assertEqual(files["src/App.jsx"], app._compile(app.validate_spec(SPEC), "novamart-test")[
            list(app.OUTPUTS).index("src/App.jsx")]["content"])

    def test_invalid_model_data_fails_without_writing_or_retry(self):
        invalid = []
        for mutation in (
            ("products", []),
            ("accent", "red; background:url(https://outside.invalid)"),
            ("categories", SPEC["categories"][:1]),
            ("brand", ""),
            ("products", [{**SPEC["products"][0], "price": True}, *SPEC["products"][1:]]),
            ("products", [{**SPEC["products"][0], "category": "../escape"}, *SPEC["products"][1:]]),
        ):
            data = deepcopy(SPEC)
            data[mutation[0]] = mutation[1]
            invalid.append(data)
        for idx, case in enumerate(invalid):
            with self.subTest(case=idx):
                with patch("agentforge.model.generate_json", return_value=case) as model:
                    with self.assertRaisesRegex(ValueError, "APP_SPEC_INVALID"):
                        app.propose("novamart-test", BRIEF)
                    model.assert_called_once()
                self.assertFalse(app.PROPOSALS.exists())

    def test_explicit_sha_is_required_to_write_and_never_runs_npm(self):
        receipt = self._propose()
        with self.assertRaises(PermissionError):
            app.apply(receipt["proposal_id"], sha256=receipt["sha256"])
        with self.assertRaises(PermissionError):
            app.apply(receipt["proposal_id"], confirm_write=True, sha256="0" * 64)
        with (patch("subprocess.run") as proc,
              patch("subprocess.Popen") as popen):
            result = app.apply(receipt["proposal_id"], confirm_write=True,
                               sha256=receipt["sha256"])
            proc.assert_not_called()
            popen.assert_not_called()
        self.assertEqual(result["status"], "FILES_WRITTEN_NOT_EXECUTED")
        self.assertTrue((app.PROJECTS / "novamart-test" / "src" / "App.jsx").is_file())
        self.assertTrue((app.PROJECTS / "novamart-test" / "tests" / "store.test.js").is_file())
        with self.assertRaises(FileExistsError):
            app.apply(receipt["proposal_id"], confirm_write=True,
                      sha256=receipt["sha256"])

    def test_signed_proposal_rejects_tampering(self):
        receipt = self._propose()
        _, path = app._read_proposal(receipt["proposal_id"])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["files"][0]["content"] += "\nchanged"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            app._read_proposal(receipt["proposal_id"])
        self.assertFalse(app.PROJECTS.exists())

    def test_no_autoretry_on_model_outage_and_symlink_output_block(self):
        with patch("agentforge.model.generate_json", side_effect=RuntimeError("gateway down")) as model:
            with self.assertRaises(RuntimeError):
                app.propose("novamart-test", BRIEF)
            model.assert_called_once()
        self.assertFalse(app.PROPOSALS.exists())
        outside = self.root / "outside"
        outside.mkdir()
        app.PROJECTS.parent.mkdir(parents=True, exist_ok=True)
        try:
            app.PROJECTS.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink privilege unavailable")
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises(PermissionError):
                app.propose("novamart-test", BRIEF)
            model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
