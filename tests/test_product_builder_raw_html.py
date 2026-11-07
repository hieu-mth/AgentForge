"""Production web.create: variable AI design spec -> offline, SHA-gated files."""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder as builder, product_quality
from agentforge.domains.websites.ai_designer import DESIGN_SCHEMA, render, validate_spec
from agentforge.domains.websites.structured_builder import owner_phone
from tests.designer_fixture import DESIGN, revised_design, longer_design

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
        answer = DESIGN if data is None else data
        with (patch("agentforge.model.generate_json", return_value=answer) as model,
              patch("agentforge.model.generate") as raw):
            receipt = builder.propose("portfolio-demo", BRIEF)
            model.assert_called_once()
            self.assertEqual(model.call_args.kwargs, {"worker_id": "product_builder"})
            self.assertEqual(model.call_args.args[1], DESIGN_SCHEMA)
            self.assertIn(BRIEF, model.call_args.args[0])
            raw.assert_not_called()
        return receipt

    def test_one_model_call_creates_only_review_proposal_with_editable_design(self):
        receipt = self._create()
        self.assertFalse(builder.PRODUCTS.exists())
        doc = json.loads(Path(receipt["proposal_path"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["status"], "PROPOSED_NOT_APPLIED")
        self.assertFalse(doc["execution_authorized"])
        self.assertFalse(doc["spending_authorized"])
        self.assertFalse(doc["deployment_authorized"])
        self.assertEqual([x["path"] for x in doc["files"]], ["index.html", "site.json"])
        source = doc["files"][0]["content"]
        self.assertIn(DESIGN["hero"]["headline"], source)
        self.assertIn(DESIGN["brand"], source)
        self.assertIn("Content-Security-Policy", source)
        self.assertIn("prefers-reduced-motion", source)
        self.assertIn("grid-template-columns", source)
        self.assertIn('lang="vi"', source)
        self.assertIn('href="#contact"', source)
        self.assertNotIn("<script", source)
        self.assertNotIn("https://", source)
        self.assertEqual(json.loads(doc["files"][1]["content"]),
                         {"format": "agentforge.design.v1", "design": validate_spec(DESIGN)})
        self.assertNotEqual(product_quality.analyze(source)["status"], "FAIL")
        self.assertLess(len(source.encode("utf-8")), builder.MAX_FILE_BYTES)

    def test_model_copy_is_escaped_and_never_executes_as_markup(self):
        attack = deepcopy(DESIGN)
        attack["hero"]["headline"] = '<script>alert("x")</script>'
        attack["hero"]["description"] = 'Ảnh ở https://invalid.example/image.jpg'
        attack["sections"][0]["items"][0]["body"] = '@import url(data:text/html,x) <img onerror=alert(1)>'
        receipt = self._create(attack)
        doc = json.loads(Path(receipt["proposal_path"]).read_text(encoding="utf-8"))
        source = doc["files"][0]["content"]
        self.assertIn("&lt;script&gt;", source)
        self.assertIn("&lt;img", source)
        self.assertNotIn("<script>", source)
        self.assertNotIn("https://invalid.example", source)
        self.assertNotIn("@import", source)
        self.assertIsNone(builder._suspicious_match(source))
        self.assertNotEqual(product_quality.analyze(source)["status"], "FAIL")

    def test_two_different_ai_designs_generate_genuinely_different_pages(self):
        a = render(DESIGN)
        b = render(longer_design())
        self.assertNotEqual(a, b)
        self.assertIn('class="wrapper hero hero-editorial"', b)
        self.assertIn('class="section section--gallery', b)
        self.assertIn('class="section section--steps', b)
        self.assertIn("--accent:#d2ac6b", b)
        self.assertNotIn('class="section section--steps', a)
        self.assertNotEqual(product_quality.analyze(b)["status"], "FAIL")

    def test_low_contrast_ai_accent_uses_readable_text_fallback(self):
        poor = deepcopy(DESIGN)
        poor["style"].update({"background": "#ffffff", "surface": "#ffffff",
                              "accent": "#fdfdfd"})
        html = render(poor)
        self.assertIn("--accent:#fdfdfd", html)
        self.assertIn("--label-ink:#17212b", html)
        self.assertIn("--accent-ink:#17212b", html)
        self.assertNotEqual(product_quality.analyze(html)["status"], "FAIL")

    def test_legacy_html_parser_still_rejects_untrusted_code(self):
        fence = chr(96) * 3
        self.assertEqual(builder._standalone_html(fence + "html\n" + GOOD + "\n" + fence), GOOD)
        for bad in ['{"files":', "Explanation: " + GOOD, GOOD[:-18]]:
            with self.subTest(bad=bad[:20]), self.assertRaises(ValueError):
                builder._standalone_html(bad)

    def test_invalid_model_design_fails_without_proposal(self):
        bad_style = deepcopy(DESIGN)
        bad_style["style"]["accent"] = "red;url(https://bad.example)"
        bad_kind = deepcopy(DESIGN)
        bad_kind["sections"][0]["kind"] = "script"
        no_sections = deepcopy(DESIGN)
        no_sections["sections"] = []
        bad_font = deepcopy(DESIGN)
        bad_font["style"]["font"] = "https://evil.example/font.css"
        for idx, data in enumerate([
            {"brand": "Only a brand"}, bad_style, bad_kind, no_sections, bad_font,
            {**DESIGN, "brand": ""}, {**DESIGN, "page_title": "T" * 111},
        ]):
            with self.subTest(case=idx):
                with patch("agentforge.model.generate_json", return_value=data) as model:
                    with self.assertRaisesRegex(ValueError, "AI_DESIGN_INVALID"):
                        builder.propose("portfolio-demo", BRIEF)
                    model.assert_called_once()
                self.assertFalse(builder.PROPOSALS.exists())

    def test_no_auto_retry_or_fabricated_success_on_model_outage(self):
        with patch("agentforge.model.generate_json", side_effect=RuntimeError("Offline gateway unavailable")) as model:
            with self.assertRaises(RuntimeError):
                builder.propose("portfolio-demo", BRIEF)
            model.assert_called_once()
        self.assertFalse(builder.PROPOSALS.exists())

    def test_long_content_stays_within_bounded_file_contract(self):
        maximal = longer_design()
        maximal["brand"] = "B" * 64
        maximal["page_title"] = "T" * 110
        maximal["description"] = "D" * 210
        maximal["hero"]["headline"] = "H" * 110
        maximal["hero"]["description"] = "L" * 300
        maximal["sections"] = [deepcopy(maximal["sections"][1]) for _ in range(7)]
        for section in maximal["sections"]:
            section["items"] = [{"title": "T" * 105, "body": "D" * 240} for _ in range(4)]
        html = render(maximal)
        self.assertLess(len(html.encode("utf-8")), builder.MAX_FILE_BYTES)
        self.assertNotEqual(product_quality.analyze(html)["status"], "FAIL")

    def test_sha_still_required_to_apply_both_files(self):
        receipt = self._create()
        with self.assertRaises(PermissionError):
            builder.apply(receipt["proposal_id"], sha256=receipt["sha256"])
        with self.assertRaises(PermissionError):
            builder.apply(receipt["proposal_id"], sha256="0" * 64, confirm_write=True)
        done = builder.apply(receipt["proposal_id"], sha256=receipt["sha256"], confirm_write=True)
        self.assertEqual(done["status"], "FILES_WRITTEN_NOT_EXECUTED")
        self.assertTrue((builder.PRODUCTS / "portfolio-demo" / "index.html").is_file())
        self.assertTrue((builder.PRODUCTS / "portfolio-demo" / "site.json").is_file())
        with self.assertRaises(FileExistsError):
            builder.apply(receipt["proposal_id"], sha256=receipt["sha256"], confirm_write=True)

    def test_owner_phone_is_not_invented_and_invalid_number_is_rejected(self):
        self.assertEqual(owner_phone("Liên hệ 0879547988 để tư vấn"), "0879547988")
        self.assertIsNone(owner_phone("Chưa có số điện thoại"))
        with patch("agentforge.model.generate_json", return_value=DESIGN):
            receipt = builder.propose("portfolio-demo", BRIEF + " Hotline 0879547988")
        doc = json.loads(Path(receipt["proposal_path"]).read_text(encoding="utf-8"))
        html = doc["files"][0]["content"]
        self.assertIn('href="tel:0879547988"', html)
        self.assertNotEqual(product_quality.analyze(html)["status"], "FAIL")
        with self.assertRaises(ValueError):
            render(DESIGN, phone="https://host.invalid")

    def test_renderer_has_no_network_process_or_model_call(self):
        with (patch("subprocess.run") as process,
              patch("urllib.request.urlopen") as network,
              patch("agentforge.model.generate_json") as model):
            rendered = render(DESIGN)
            process.assert_not_called()
            network.assert_not_called()
            model.assert_not_called()
        self.assertIn("Trải nghiệm tư vấn", rendered)


if __name__ == "__main__":
    unittest.main()
