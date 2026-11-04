"""C8D browser tests use a fake Playwright adapter (CI needs no browser)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentforge import browser_validation as bv
from agentforge import product_builder as builder
from agentforge import product_revision as revision

HTML = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Shop</title><style>@media(max-width:600px){body{margin:0}}'
        '</style></head><body><h1>Shop</h1></body></html>')
NEW = HTML.replace('Shop</h1>', 'Đổi mới</h1>')
REQUEST = "Improve small-screen layout and keep the current content and colors."


class FakePage:
    def __init__(self, ctx):
        self.ctx = ctx
        self.events = {}
        self.main_fulfilled = False
        self.blocked = False

    def on(self, name, cb):
        self.events[name] = cb

    def goto(self, url, **kwargs):
        assert url == bv.DOCUMENT_URL
        self._request(url, "document")
        assert self.main_fulfilled
        if self.ctx.parent.block_network:
            self._request("https://example.invalid/track.png", "image")
        if self.ctx.parent.raise_js_error:
            self.events["pageerror"](RuntimeError("example script failed"))

    def _request(self, url, kind):
        req = SimpleNamespace(url=url, method="GET", resource_type=kind)
        page = self

        class Route:
            request = req

            def fulfill(self, **kwargs):
                page.main_fulfilled = True
                assert kwargs["content_type"].startswith("text/html")
                assert kwargs["body"] == HTML.encode("utf-8") or kwargs["body"] == NEW.encode("utf-8")

            def abort(self, reason):
                assert reason == "blockedbyclient"
                page.blocked = True

        self.ctx.route_handler(Route())

    def wait_for_timeout(self, time_ms):
        assert time_ms <= 500

    def evaluate(self, script):
        assert "document.documentElement" in script
        width = self.ctx.width
        overflow = 25 if self.ctx.parent.overflow and width == 390 else 0
        height = 18000 if self.ctx.parent.tall else 1400
        return {
            "viewport_width": width,
            "document_width": width + overflow,
            "document_height": height,
            "title_present": True,
        }

    def screenshot(self, **kwargs):
        assert kwargs["full_page"] is True
        assert kwargs["animations"] == "disabled"
        Path(kwargs["path"]).write_bytes(b"\x89PNG\r\n\x1a\nFAKE")


class FakeContext:
    def __init__(self, parent, args):
        self.parent = parent
        self.width = args["viewport"]["width"]
        self.params = args
        self.closed = False

    def route(self, pattern, callback):
        assert pattern == "**/*"
        self.route_handler = callback

    def new_page(self):
        return FakePage(self)

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, harness):
        self.harness = harness
        self.contexts = []
        self.closed = False

    def new_context(self, **kwargs):
        assert kwargs["service_workers"] == "block"
        assert kwargs["accept_downloads"] is False
        assert kwargs["permissions"] == []
        ctx = FakeContext(self.harness, kwargs)
        self.contexts.append(ctx)
        return ctx

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, *, overflow=False, block_network=False,
                 raise_js_error=False, tall=False):
        self.overflow = overflow
        self.block_network = block_network
        self.raise_js_error = raise_js_error
        self.tall = tall
        self.browser = FakeBrowser(self)
        self.chromium = self
        self.entered = False
        self.channel = None

    def __call__(self):
        return self

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *args):
        pass

    def launch(self, *, headless, channel=None):
        assert headless is True
        self.channel = channel
        return self.browser


class TestBrowserValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch_root = patch.object(builder, "ROOT", self.root)
        self.patch_products = patch.object(
            builder, "PRODUCTS", self.root / "workspace" / "products")
        self.patch_root.start()
        self.patch_products.start()
        self.file = builder.PRODUCTS / "shop-landing" / "index.html"
        self.file.parent.mkdir(parents=True)
        self.file.write_text(HTML, encoding="utf-8")

    def tearDown(self):
        self.patch_products.stop()
        self.patch_root.stop()
        self.tmp.cleanup()

    def propose(self):
        return revision.propose(
            "shop-landing", REQUEST,
            model_client=lambda prompt, *, worker_id: NEW,
        )

    def run_project(self, **kwargs):
        fake = FakePlaywright(**kwargs)
        result = bv.validate("project", "shop-landing",
                             confirm_browser_run=True, playwright_factory=fake)
        return result, fake

    def test_explicit_owner_approval_is_required(self):
        fake = FakePlaywright()
        with self.assertRaises(PermissionError):
            bv.validate("project", "shop-landing", playwright_factory=fake)
        self.assertFalse(fake.entered)
        self.assertFalse((self.root / "data").exists())

    def test_unknown_target_is_rejected(self):
        with self.assertRaises(ValueError):
            bv.validate("all", "shop-landing", confirm_browser_run=True,
                        playwright_factory=FakePlaywright())

    def test_invalid_slug_is_rejected(self):
        with self.assertRaises(ValueError):
            bv.validate("project", "../escape", confirm_browser_run=True,
                        playwright_factory=FakePlaywright())

    def test_missing_project_is_rejected_before_browser(self):
        fake = FakePlaywright()
        with self.assertRaises(FileNotFoundError):
            bv.validate("project", "not-found", confirm_browser_run=True,
                        playwright_factory=fake)
        self.assertFalse(fake.entered)

    def test_static_fail_refuses_to_execute_browser(self):
        self.file.write_text(HTML.replace("<h1>Shop</h1>", '<h1 onclick="alert(1)">Shop</h1>'),
                             encoding="utf-8")
        fake = FakePlaywright()
        with self.assertRaisesRegex(ValueError, "Static checks report FAIL"):
            bv.validate("project", "shop-landing", confirm_browser_run=True,
                        playwright_factory=fake)
        self.assertFalse(fake.entered)

    def test_project_checks_three_viewports_and_screenshots(self):
        old = self.file.read_bytes()
        result, fake = self.run_project()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["screenshots"]), 3)
        self.assertTrue(all(Path(p).is_file() for p in result["screenshots"]))
        self.assertEqual(self.file.read_bytes(), old)
        self.assertTrue(fake.browser.closed)
        self.assertTrue(all(ctx.closed for ctx in fake.browser.contexts))
        self.assertEqual([ctx.width for ctx in fake.browser.contexts],
                         [390, 768, 1440])
        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertTrue(report["browser_rendered"])
        self.assertTrue(report["javascript_executed"])
        self.assertFalse(report["security_verified"])
        self.assertFalse(report["deployment_authorized"])
        self.assertFalse(report["product_modified"])
        self.assertEqual(report["source_sha256"], revision._hash(old))

    def test_horizontal_overflow_detected(self):
        result, _ = self.run_project(overflow=True)
        self.assertEqual(result["status"], "FAIL")
        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertEqual(report["findings"][0]["rule"], "horizontal_overflow")
        self.assertEqual(report["findings"][0]["viewport"], "mobile")

    def test_uncaught_javascript_error_detected(self):
        result, _ = self.run_project(raise_js_error=True)
        self.assertEqual(result["status"], "FAIL")
        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertTrue(any(i["rule"] == "javascript_errors" for i in report["findings"]))

    def test_off_document_requests_are_blocked_and_counted(self):
        result, _ = self.run_project(block_network=True)
        self.assertEqual(result["status"], "FAIL")
        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertEqual(report["viewports"][0]["blocked_request_count"], 1)
        self.assertTrue(any(i["rule"] == "blocked_requests" for i in report["findings"]))
        self.assertNotIn("https://example.invalid", str(report))

    def test_page_too_tall_skips_screenshots(self):
        result, _ = self.run_project(tall=True)
        self.assertEqual(result["status"], "WARN")
        self.assertEqual(result["screenshots"], [])
        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertEqual(report["warnings"], 3)
        self.assertTrue(all(x["screenshot_path"] is None for x in report["viewports"]))

    def test_each_run_generates_immutable_distinct_report(self):
        first, _ = self.run_project()
        second, _ = self.run_project()
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertTrue(Path(first["report_path"]).exists())
        self.assertTrue(Path(second["report_path"]).exists())

    def test_pending_revision_browser_validates_without_apply(self):
        doc = self.propose()
        fake = FakePlaywright()
        result = bv.validate("revision", doc["revision_id"],
                             confirm_browser_run=True, playwright_factory=fake)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(self.file.read_text(encoding="utf-8"), HTML)
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "applied").exists())

    def test_applied_revision_cannot_run_again(self):
        doc = self.propose()
        revision.apply(doc["revision_id"], confirm_write=True,
                       sha256=doc["sha256"])
        fake = FakePlaywright()
        with self.assertRaisesRegex(RuntimeError, "already applied"):
            bv.validate("revision", doc["revision_id"],
                        confirm_browser_run=True, playwright_factory=fake)
        self.assertFalse(fake.entered)

    def test_stale_revision_refuses_to_launch(self):
        doc = self.propose()
        self.file.write_text(HTML.replace('Shop</title>', 'Updated</title>'),
                             encoding="utf-8")
        fake = FakePlaywright()
        with self.assertRaisesRegex(RuntimeError, "STALE_REVISION"):
            bv.validate("revision", doc["revision_id"],
                        confirm_browser_run=True, playwright_factory=fake)
        self.assertFalse(fake.entered)

    def test_approval_does_not_call_model_or_network(self):
        fake = FakePlaywright()
        with (patch("agentforge.model.generate") as model,
              patch("urllib.request.urlopen") as urlopen,
              patch("subprocess.run") as shell):
            bv.validate("project", "shop-landing",
                        confirm_browser_run=True, playwright_factory=fake)
            model.assert_not_called()
            urlopen.assert_not_called()
            shell.assert_not_called()

    def test_bundled_remains_default_with_no_channel(self):
        result, fake = self.run_project()
        self.assertEqual(result["browser_channel"], "bundled")
        self.assertIsNone(fake.channel)

    def test_installed_microsoft_edge_channel(self):
        fake = FakePlaywright()
        result = bv.validate(
            "project", "shop-landing", confirm_browser_run=True,
            playwright_factory=fake, browser_channel="msedge",
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(fake.channel, "msedge")
        self.assertEqual(result["browser_channel"], "msedge")
        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        self.assertEqual(report["browser_channel"], "msedge")
        self.assertTrue(report["browser_rendered"])

    def test_installed_google_chrome_channel(self):
        fake = FakePlaywright()
        result = bv.validate(
            "project", "shop-landing", confirm_browser_run=True,
            playwright_factory=fake, browser_channel="chrome",
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(fake.channel, "chrome")
        self.assertEqual(len(result["screenshots"]), 3)

    def test_unsupported_browser_channel_rejected_before_browser(self):
        fake = FakePlaywright()
        with self.assertRaisesRegex(ValueError, "Unsupported browser channel"):
            bv.validate(
                "project", "shop-landing", confirm_browser_run=True,
                playwright_factory=fake, browser_channel="custom-binary",
            )
        self.assertFalse(fake.entered)
        self.assertFalse((self.root / "data").exists())

    def test_browser_channel_does_not_bypass_owner_consent(self):
        fake = FakePlaywright()
        with self.assertRaises(PermissionError):
            bv.validate(
                "project", "shop-landing",
                playwright_factory=fake, browser_channel="msedge",
            )
        self.assertFalse(fake.entered)

    def test_browser_import_is_lazy(self):
        with patch.object(bv, "_playwright", side_effect=RuntimeError("install Playwright")):
            with self.assertRaisesRegex(RuntimeError, "install Playwright"):
                bv.validate("project", "shop-landing", confirm_browser_run=True)
        self.assertFalse((self.root / "data").exists())

    def test_revision_with_static_fail_refuses_execution(self):
        doc = self.propose()
        path, _ = revision._paths(doc["revision_id"])
        # No editing a signed proposal: tampering must be rejected by C8B.
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj["files"][0]["content"] = HTML.replace("<h1>Shop</h1>", '<h1 onclick="bad()">Shop</h1>')
        path.write_text(json.dumps(obj), encoding="utf-8")
        with self.assertRaises(ValueError):
            bv.validate("revision", doc["revision_id"],
                        confirm_browser_run=True, playwright_factory=FakePlaywright())


if __name__ == "__main__":
    unittest.main()
