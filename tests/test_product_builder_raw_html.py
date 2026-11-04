"""C8A hotfix: plain HTML model output, no JSON-escaped source required."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder as b


GOOD = '<!doctype html><html lang="vi"><head><style>body{margin:0}</style></head><body><h1>Xin chào</h1></body></html>'


class TestProductBuilderRawHtml(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch.object(b, "ROOT", self.root),
            patch.object(b, "WORKSPACE", self.root / "workspace"),
            patch.object(b, "PRODUCTS", self.root / "workspace" / "products"),
            patch.object(b, "PROPOSALS", self.root / "data" / "company" / "product_builder" / "proposals"),
        ]
        for p in self.patches:
            p.start()
        self.brief = "Make a compact attractive Vietnamese landing page for Excel services."

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_default_calls_plain_text_generation_without_json(self):
        with (patch("agentforge.model.generate", return_value=GOOD) as generate,
              patch("agentforge.model.generate_json") as generate_json):
            proposal = b.propose("shop-landing", self.brief)
            generate.assert_called_once()
            self.assertEqual(generate.call_args.kwargs, {"worker_id": "product_builder"})
            self.assertIn("Return ONLY raw HTML", generate.call_args.args[0])
            generate_json.assert_not_called()
        document = json.loads(Path(proposal["proposal_path"]).read_text(encoding="utf-8"))
        self.assertEqual([x["path"] for x in document["files"]], ["index.html"])
        html = document["files"][0]["content"]
        self.assertIn("<h1>Xin chào</h1>", html)
        self.assertIn("agentforge-web-design-v2", html)
        self.assertIn("Segoe UI", html)
        self.assertIn("prefers-reduced-motion", html)
        self.assertIn("Minh họa đồ họa trang trí", html)
        self.assertFalse(b.PRODUCTS.exists())
        self.assertFalse(document["execution_authorized"])

    def test_realistic_inline_svg_xmlns_is_not_an_external_request(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
               'xmlns:xlink="http://www.w3.org/1999/xlink" '
               'viewBox="0 0 20 20"><circle cx="10" cy="10" r="5"/></svg>')
        illustrated = GOOD.replace("<h1>Xin chào</h1>",
                                   "<h1>Xin chào</h1>" + svg)
        with patch("agentforge.model.generate", return_value=illustrated) as generate:
            proposal = b.propose("shop-landing", self.brief)
            generate.assert_called_once()
        doc = json.loads(Path(proposal["proposal_path"]).read_text(encoding="utf-8"))
        html = doc["files"][0]["content"]
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', html)
        self.assertIn("agentforge-web-design-v2", html)
        from agentforge import product_quality as quality
        findings = quality.analyze(html)["findings"]
        self.assertNotIn("unsafe_content", [item["rule"] for item in findings])

    def test_non_namespace_network_urls_still_rejected(self):
        examples = [
            '<img src="https://example.org/tracker.png">',
            '<svg><image href="http://www.w3.org/2000/svg"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.org/x.png"/></svg>',
            '<script>fetch("/api")</script>',
        ]
        for payload in examples:
            with self.subTest(payload=payload[:30]):
                bad = GOOD.replace("<h1>", payload + "<h1>")
                with patch("agentforge.model.generate", return_value=bad):
                    with self.assertRaisesRegex(ValueError, "Disallowed active/remote"):
                        b.propose("shop-landing", self.brief)
        self.assertFalse(b.PROPOSALS.exists())

    def test_unsafe_error_identifies_category_and_line(self):
        bad = GOOD.replace("<h1>", "\n<a href='https://example.org'>Link</a>\n<h1>")
        with patch("agentforge.model.generate", return_value=bad) as generate:
            with self.assertRaisesRegex(ValueError, r"remote URL at line 2"):
                b.propose("shop-landing", self.brief)
            generate.assert_called_once()
        self.assertFalse(b.PROPOSALS.exists())

    def test_model_specific_svg_skips_neutral_fallback(self):
        illustrated = GOOD.replace(
            "<h1>Xin chào</h1>",
            "<h1>Xin chào</h1><svg role='img' viewBox='0 0 20 20'></svg>",
        )
        with patch("agentforge.model.generate", return_value=illustrated) as generate:
            proposal = b.propose("shop-landing", self.brief)
            generate.assert_called_once()
        doc = json.loads(Path(proposal["proposal_path"]).read_text(encoding="utf-8"))
        html = doc["files"][0]["content"]
        self.assertIn("viewBox='0 0 20 20'", html)
        self.assertNotIn("Minh họa đồ họa trang trí", html)
        self.assertIn("agentforge-web-design-v2", html)

    def test_premium_output_still_respects_file_size_limit(self):
        enormous = GOOD.replace("</body>", "<p>" + "x" * 15000 + "</p></body>")
        with patch("agentforge.model.generate", return_value=enormous) as generate:
            with self.assertRaisesRegex(ValueError, "too large"):
                b.propose("shop-landing", self.brief)
            generate.assert_called_once()
        self.assertFalse(b.PROPOSALS.exists())

    def test_optional_single_markdown_html_fence(self):
        with patch("agentforge.model.generate", return_value="```html\n" + GOOD + "\n```"):
            proposal = b.propose("shop-landing", self.brief)
        doc = json.loads(Path(proposal["proposal_path"]).read_text(encoding="utf-8"))
        self.assertIn("<h1>Xin chào</h1>", doc["files"][0]["content"])
        self.assertIn("agentforge-web-design-v2", doc["files"][0]["content"])

    def test_incomplete_html_rejected_without_proposal(self):
        with patch("agentforge.model.generate", return_value=GOOD[:75]):
            with self.assertRaisesRegex(ValueError, "truncated or incomplete"):
                b.propose("shop-landing", self.brief)
        self.assertFalse(b.PROPOSALS.exists())
        self.assertFalse(b.PRODUCTS.exists())

    def test_raw_json_or_prose_rejected_without_files(self):
        for bad in ('{"files":', 'Here is your HTML:\n' + GOOD, "```html\n" + GOOD):
            with self.subTest(bad=bad[:20]):
                with patch("agentforge.model.generate", return_value=bad):
                    with self.assertRaises(ValueError):
                        b.propose("shop-landing", self.brief)
        self.assertFalse(b.PROPOSALS.exists())

    def test_remote_code_rejected_even_in_valid_html(self):
        bad = GOOD.replace('<h1>', '<script>fetch("https://example.org")</script><h1>')
        with patch("agentforge.model.generate", return_value=bad):
            with self.assertRaisesRegex(ValueError, "Disallowed"):
                b.propose("shop-landing", self.brief)
        self.assertFalse(b.PROPOSALS.exists())

    def test_no_automatic_retry_or_silent_repair_on_model_error(self):
        with patch("agentforge.model.generate", side_effect=RuntimeError("Gateway error")) as gen:
            with self.assertRaises(RuntimeError):
                b.propose("shop-landing", self.brief)
            gen.assert_called_once()
        self.assertFalse(b.PROPOSALS.exists())

    def test_approved_apply_still_requires_matching_digest(self):
        with patch("agentforge.model.generate", return_value=GOOD):
            proposal = b.propose("shop-landing", self.brief)
        with self.assertRaises(PermissionError):
            b.apply(proposal["proposal_id"], sha256=proposal["sha256"])
        with self.assertRaises(PermissionError):
            b.apply(proposal["proposal_id"], confirm_write=True, sha256="0"*64)
        self.assertFalse(b.PRODUCTS.exists())

    def test_valid_single_file_can_apply_only_after_explicit_approval(self):
        with patch("agentforge.model.generate", return_value=GOOD):
            proposal = b.propose("shop-landing", self.brief)
        res = b.apply(proposal["proposal_id"], confirm_write=True, sha256=proposal["sha256"])
        self.assertEqual(res["status"], "FILES_WRITTEN_NOT_EXECUTED")
        applied_html = (Path(res["project_path"]) / "index.html").read_text(encoding="utf-8")
        self.assertIn("agentforge-web-design-v2", applied_html)
        self.assertIn("<h1>Xin chào</h1>", applied_html)
        self.assertFalse(res["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
