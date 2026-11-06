"""web.create production: structured model copy, safe deterministic template."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder as builder, product_quality
from agentforge.domains.websites.structured_builder import COPY_SCHEMA, render

COPY = {
    "brand": "Minh Studio",
    "headline": "Ảnh đẹp kể câu chuyện của bạn",
    "subtitle": "Portfolio nhiếp ảnh phong cách tinh giản với bố cục nhiều khoảng trắng.",
    "introduction": "Giới thiệu phong cách ảnh, cách làm việc và hướng kết nối trực tiếp.",
    "highlights": [
        {"title": "Chân dung", "description": "Lưu lại những khoảnh khắc tự nhiên."},
        {"title": "Không gian", "description": "Góc nhìn giàu chất liệu và cảm xúc."},
        {"title": "Câu chuyện", "description": "Bố cục có chủ đích, dễ đọc trên điện thoại."},
    ],
    "call_to_action": "Bắt đầu trao đổi về ý tưởng của bạn",
}
BRIEF = "Thiết kế website portfolio cho nhiếp ảnh gia Việt Nam, phong cách tối giản."
GOOD = '<!doctype html><html lang="vi"><head><style>body{margin:0}</style></head><body><h1>Xin chào</h1></body></html>'


class TestReliableWebBuilder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch.object(builder, "ROOT", self.root),
            patch.object(builder, "WORKSPACE", self.root / "workspace"),
            patch.object(builder, "PRODUCTS", self.root / "workspace" / "products"),
            patch.object(builder, "PROPOSALS", self.root / "data" / "company" / "product_builder" / "proposals"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def _create(self, data=None):
        answer = COPY if data is None else data
        with (patch("agentforge.model.generate_json", return_value=answer) as model,
              patch("agentforge.model.generate") as raw):
            receipt = builder.propose("portfolio-demo", BRIEF)
            model.assert_called_once()
            self.assertEqual(model.call_args.kwargs, {"worker_id": "product_builder"})
            self.assertEqual(model.call_args.args[1], COPY_SCHEMA)
            self.assertIn(BRIEF, model.call_args.args[0])
            raw.assert_not_called()
        return receipt

    def test_one_structured_model_call_creates_only_review_proposal(self):
        receipt = self._create()
        self.assertFalse(builder.PRODUCTS.exists())
        doc = json.loads(Path(receipt["proposal_path"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["status"], "PROPOSED_NOT_APPLIED")
        self.assertFalse(doc["execution_authorized"])
        self.assertFalse(doc["spending_authorized"])
        self.assertFalse(doc["deployment_authorized"])
        self.assertEqual(len(doc["files"]), 1)
        source = doc["files"][0]["content"]
        self.assertIn("<h1 id=\"hero-heading\">Ảnh đẹp", source)
        self.assertIn("Minh Studio", source)
        self.assertIn("Content-Security-Policy", source)
        self.assertIn("prefers-reduced-motion", source)
        self.assertIn("grid-template-columns", source)
        self.assertIn('lang="vi"', source)
        self.assertIn('href="#lien-he"', source)
        self.assertNotIn("<script", source)
        self.assertNotIn('src="https:', source)
        report = product_quality.analyze(source)
        self.assertNotEqual(report["status"], "FAIL", report["findings"])
        self.assertLess(len(source.encode("utf-8")), builder.MAX_FILE_BYTES)

    def test_model_text_never_becomes_html_code_or_remote_resource(self):
        attack = dict(COPY)
        attack["headline"] = '<script>alert("x")</script>'
        attack["subtitle"] = 'Ảnh ở https://example.invalid/image.jpg và fetch("/api")'
        attack["introduction"] = '@import url(data:text/html,whatever) <img src=x onerror=alert(1)>'
        receipt = self._create(attack)
        doc = json.loads(Path(receipt["proposal_path"]).read_text(encoding="utf-8"))
        source = doc["files"][0]["content"]
        self.assertIn("&lt;script&gt;", source)
        self.assertIn("&lt;img", source)
        self.assertNotIn("<script>", source)
        self.assertNotIn("https://example.invalid", source)
        self.assertNotIn("@import", source)
        self.assertIsNone(builder._suspicious_match(source))
        self.assertNotEqual(product_quality.analyze(source)["status"], "FAIL")

    def test_legacy_html_parser_rejects_untrusted_raw_code(self):
        fence = chr(96) * 3
        self.assertEqual(builder._standalone_html(fence + "html\n" + GOOD + "\n" + fence), GOOD)
        for bad in ['{"files":', "Explanation: " + GOOD, GOOD[:-18]]:
            with self.subTest(bad=bad[:20]):
                with self.assertRaises(ValueError):
                    builder._standalone_html(bad)

    def test_invalid_model_json_fails_without_proposal(self):
        cases = [
            {"brand": "Only a brand"},
            {**COPY, "highlights": []},
            {**COPY, "headline": ""},
            {**COPY, "headline": "x" * 101},
            {**COPY, "highlights": [{"title": "One", "description": "Only one"}]},
            {**COPY, "highlights": [COPY["highlights"][0], {"title": "Two", "description": ""}]},
        ]
        for idx, data in enumerate(cases):
            with self.subTest(case=idx):
                with patch("agentforge.model.generate_json", return_value=data) as model:
                    with self.assertRaisesRegex(ValueError, "Structured website content invalid"):
                        builder.propose("portfolio-demo", BRIEF)
                    model.assert_called_once()
                self.assertFalse(builder.PROPOSALS.exists())

    def test_no_model_auto_retry_or_fabricated_success_on_outage(self):
        with patch("agentforge.model.generate_json", side_effect=RuntimeError("Offline gateway unavailable")) as model:
            with self.assertRaises(RuntimeError):
                builder.propose("portfolio-demo", BRIEF)
            model.assert_called_once()
        self.assertFalse(builder.PROPOSALS.exists())

    def test_html_maximum_allowed_copy_stays_bounded(self):
        maximal = {
            "brand": "B" * 64, "headline": "H" * 100,
            "subtitle": "S" * 210, "introduction": "I" * 380,
            "highlights": [{"title": "T" * 65, "description": "D" * 185} for _ in range(4)],
            "call_to_action": "C" * 120,
        }
        html = render(maximal)
        self.assertLess(len(html.encode("utf-8")), builder.MAX_FILE_BYTES)
        self.assertNotEqual(product_quality.analyze(html)["status"], "FAIL")

    def test_review_sha_still_required_to_apply(self):
        receipt = self._create()
        with self.assertRaises(PermissionError):
            builder.apply(receipt["proposal_id"], sha256=receipt["sha256"])
        with self.assertRaises(PermissionError):
            builder.apply(receipt["proposal_id"], sha256="0" * 64, confirm_write=True)
        done = builder.apply(receipt["proposal_id"], sha256=receipt["sha256"], confirm_write=True)
        self.assertEqual(done["status"], "FILES_WRITTEN_NOT_EXECUTED")
        self.assertTrue((builder.PRODUCTS / "portfolio-demo" / "index.html").is_file())
        with self.assertRaises(FileExistsError):
            builder.apply(receipt["proposal_id"], sha256=receipt["sha256"], confirm_write=True)

    def test_direct_renderer_has_no_network_or_process(self):
        with (patch("subprocess.run") as process, patch("urllib.request.urlopen") as network):
            rendered = render(COPY)
            process.assert_not_called()
            network.assert_not_called()
        self.assertIn("Bắt đầu trao đổi", rendered)


if __name__ == "__main__":
    unittest.main()
