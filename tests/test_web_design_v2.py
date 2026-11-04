"""Web Design V2: gallery import, Vietnamese design kit, owner-approved flow."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import browser_validation as browser
from agentforge import product_builder as builder
from agentforge import product_revision as revision
from agentforge import product_quality as quality
from agentforge import web_assets
from agentforge import web_design_v2 as v2

HTML = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Nệm tư vấn</title><style>@media(max-width:600px){body{margin:0}}'
        '</style></head><body><main><h1>Nệm êm cho giấc ngủ Việt</h1>'
        '<section><h2>Tư vấn nệm</h2><p>Liên hệ để xem sản phẩm</p></section>'
        '</main></body></html>')
NEW = HTML.replace("Nệm êm", "Không gian ngủ cao cấp")
IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a"
    "D6kAAAAASUVORK5CYII=")
RID = "f" * 32


class TestWebDesignV2(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(builder, "ROOT", self.root),
            patch.object(builder, "WORKSPACE", self.root / "workspace"),
            patch.object(builder, "PRODUCTS", self.root / "workspace" / "products"),
        ]
        for p in self.patches:
            p.start()
        self.src = builder.PRODUCTS / "nem-tu-van" / "index.html"
        self.src.parent.mkdir(parents=True)
        self.src.write_text(HTML, encoding="utf-8")
        self.calls = []

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def model(self, prompt, *, worker_id):
        self.assertEqual(worker_id, "product_builder")
        self.calls.append(prompt)
        return NEW

    def prepare(self, **kwargs):
        return v2.prepare("nem-tu-van", confirm_model_call=True,
                          model_client=self.model, **kwargs)

    def fake_browser(self, kind, identifier, *, confirm_browser_run, browser_channel):
        self.assertTrue(confirm_browser_run)
        self.assertEqual(kind, "revision")
        doc, _, receipt = revision._read_revision(identifier)
        self.assertFalse(receipt.exists())
        path = (self.root / "data" / "company" / "product_builder" /
                "browser_checks" / "revision" / identifier / RID / "report.json")
        path.parent.mkdir(parents=True)
        report = {
            "schema_version": 1, "run_id": RID, "target": "revision",
            "identifier": identifier, "project_slug": "nem-tu-van",
            "source_sha256": revision._hash(doc["files"][0]["content"].encode("utf-8")),
            "browser_rendered": True, "browser_run_approved": True,
            "product_modified": False, "deployment_authorized": False,
            "status": "PASS", "failures": 0, "warnings": 0,
            "viewports": [{}, {}, {}], "findings": [],
        }
        path.write_text(json.dumps(report), encoding="utf-8")
        return {"run_id": RID, "status": "PASS"}

    def test_requires_owner_model_approval(self):
        with self.assertRaisesRegex(PermissionError, "confirm-model-call"):
            v2.prepare("nem-tu-van", model_client=self.model)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)

    def test_model_failure_never_changes_product(self):
        def fail(*a, **kw):
            raise RuntimeError("gateway timeout")
        with self.assertRaisesRegex(RuntimeError, "gateway"):
            v2.prepare("nem-tu-van", confirm_model_call=True, model_client=fail)
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)
        self.assertFalse(v2._latest_path("nem-tu-van").exists())

    def test_v2_adds_local_art_typography_animation(self):
        prepared = self.prepare()
        self.assertEqual(prepared["status"], "AWAITING_BROWSER_TEST")
        self.assertEqual(len(self.calls), 1)
        self.assertIn("Luxury Premium", self.calls[0])
        self.assertFalse(prepared["product_modified"])
        self.assertFalse(prepared["automatic_approval"])
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)
        html = Path(prepared["preview_path"]).read_text(encoding="utf-8")
        self.assertIn("Minh họa chiếc giường", html)
        self.assertIn("Segoe UI", html)
        self.assertIn("prefers-reduced-motion", html)
        self.assertIn("Nệm", html)
        self.assertTrue(all(prepared["style_audit"][k] for k in
                        ("utf8_meta", "vietnamese_lang", "system_font_stack",
                         "has_visual", "reduced_motion")))
        self.assertFalse(prepared["style_audit"]["aesthetic_quality_verified"])

    def test_preview_is_hashed_c8b_revision(self):
        prepared = self.prepare()
        doc, _, _ = revision._read_revision(prepared["revision_id"])
        self.assertEqual(doc["project_slug"], "nem-tu-van")
        self.assertIn("agentforge-web-design-v2", doc["files"][0]["content"])
        self.assertEqual(quality.check_revision(prepared["revision_id"])["status"], "PASS")
        self.assertEqual(v2.review("nem-tu-van")["revision_id"],
                         prepared["revision_id"])

    def test_approve_requires_both_owner_flags(self):
        self.prepare()
        with self.assertRaises(PermissionError):
            v2.approve("nem-tu-van", confirm_write=True)
        with self.assertRaises(PermissionError):
            v2.approve("nem-tu-van", confirm_reviewed=True)
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)

    def test_approve_requires_browser_pass(self):
        self.prepare()
        with self.assertRaisesRegex(PermissionError, "Passing C8D"):
            v2.approve("nem-tu-van", confirm_reviewed=True, confirm_write=True)
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)

    def test_test_requires_explicit_browser_permission(self):
        self.prepare()
        with self.assertRaisesRegex(PermissionError, "confirm-browser-run"):
            v2.test("nem-tu-van", browser_runner=self.fake_browser)

    def test_prepare_can_test_browser_with_explicit_consent(self):
        result = self.prepare(confirm_browser_run=True, browser_channel="msedge",
                              browser_runner=self.fake_browser)
        self.assertEqual(result["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(result["browser_run_id"], RID)
        self.assertEqual(result["browser_status"], "PASS")
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)

    def test_separate_browser_check_without_id_copy(self):
        self.prepare()
        result = v2.test("nem-tu-van", confirm_browser_run=True,
                         browser_channel="chrome", browser_runner=self.fake_browser)
        self.assertEqual(result["status"], "READY_FOR_OWNER_REVIEW")
        with self.assertRaisesRegex(RuntimeError, "already tested"):
            v2.test("nem-tu-van", confirm_browser_run=True,
                    browser_channel="chrome", browser_runner=self.fake_browser)

    def test_approved_revision_uses_c8b_backup_and_digest(self):
        result = self.prepare(confirm_browser_run=True, browser_runner=self.fake_browser)
        applied = v2.approve("nem-tu-van", confirm_reviewed=True,
                             confirm_write=True)
        self.assertEqual(applied["status"], "FILES_REVISED_NOT_EXECUTED")
        self.assertEqual(applied["revision_id"], result["revision_id"])
        self.assertTrue(Path(applied["backup_path"]).exists())
        self.assertEqual(Path(applied["backup_path"]).read_text(encoding="utf-8"), HTML)
        self.assertIn("agentforge-web-design-v2", self.src.read_text(encoding="utf-8"))
        self.assertEqual(v2.review("nem-tu-van")["status"], "APPLIED_VIA_C8B")
        self.assertFalse(applied["automatic_approval"])
        self.assertFalse(applied["deployment_authorized"])

    def test_cannot_approve_twice(self):
        self.prepare(confirm_browser_run=True, browser_runner=self.fake_browser)
        v2.approve("nem-tu-van", confirm_reviewed=True, confirm_write=True)
        with self.assertRaisesRegex(RuntimeError, "already applied"):
            v2.approve("nem-tu-van", confirm_reviewed=True, confirm_write=True)

    def test_broken_photo_path_prevents_preview(self):
        def bad_model(prompt, *, worker_id):
            return NEW.replace("<main>", '<main><img src="assets/absent.jpg" alt="Ảnh">')
        with self.assertRaisesRegex(ValueError, "checks FAIL"):
            v2.prepare("nem-tu-van", confirm_model_call=True, model_client=bad_model)
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)

    def test_local_png_import_requires_approval(self):
        source = self.root / "photo.png"
        source.write_bytes(IMAGE)
        with self.assertRaises(PermissionError):
            web_assets.import_image("nem-tu-van", source, "hero.png")
        result = web_assets.import_image("nem-tu-van", source, "hero.png",
                                         confirm_write=True)
        self.assertEqual(result["status"], "LOCAL_IMAGE_IMPORTED")
        self.assertEqual(web_assets.list_images("nem-tu-van")[0]["name"], "hero.png")
        with self.assertRaises(FileExistsError):
            web_assets.import_image("nem-tu-van", source, "hero.png",
                                     confirm_write=True)

    def test_invalid_asset_name_and_fake_format_rejected(self):
        source = self.root / "photo.png"
        source.write_bytes(IMAGE)
        for name in ("../hero.png", "hero.svg", "Hero.PNG", "other/hero.png"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                web_assets.import_image("nem-tu-van", source, name, confirm_write=True)
        source.write_bytes(b"not a png")
        with self.assertRaises(ValueError):
            web_assets.import_image("nem-tu-van", source, "hero.png",
                                     confirm_write=True)

    def test_asset_photo_is_added_to_preview(self):
        photo = self.root / "original.png"
        photo.write_bytes(IMAGE)
        web_assets.import_image("nem-tu-van", photo, "hero.png", confirm_write=True)
        res = self.prepare()
        self.assertEqual(res["assets"], ["hero.png"])
        content = Path(res["preview_path"]).read_text(encoding="utf-8")
        self.assertIn('src="assets/hero.png"', content)
        dest = Path(res["preview_path"]).parent / "assets" / "hero.png"
        self.assertEqual(dest.read_bytes(), IMAGE)
        self.assertNotIn("Minh họa chiếc giường", content)
        self.assertEqual(quality.check_revision(res["revision_id"])["status"], "PASS")

    def test_changed_photo_blocks_approval(self):
        source = self.root / "original.png"
        source.write_bytes(IMAGE)
        web_assets.import_image("nem-tu-van", source, "hero.png",
                                 confirm_write=True)
        self.prepare(confirm_browser_run=True, browser_runner=self.fake_browser)
        target = builder.PRODUCTS / "nem-tu-van" / "assets" / "hero.png"
        target.write_bytes(IMAGE + b"extra")
        with self.assertRaisesRegex(RuntimeError, "LOCAL_IMAGES_CHANGED"):
            v2.approve("nem-tu-van", confirm_reviewed=True, confirm_write=True)
        self.assertEqual(self.src.read_text(encoding="utf-8"), HTML)

    def test_missing_image_detected_by_static_check(self):
        html = HTML.replace("<main>", '<main><img src="assets/hero.png" alt="Nệm">')
        self.src.write_text(html, encoding="utf-8")
        status = quality.check_project("nem-tu-van")
        self.assertEqual(status["status"], "FAIL")
        self.assertIn("local_image_invalid", [x["rule"] for x in status["findings"]])

    def test_preview_tamper_rejected(self):
        res = self.prepare()
        Path(res["preview_path"]).write_text("CHANGED", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Preview missing or modified"):
            v2.review("nem-tu-van")

    def test_checkpoint_rejects_stale_product_source(self):
        self.prepare()
        self.src.write_text(HTML.replace("Nệm", "Đệm"), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            v2.review("nem-tu-van")

    def test_latest_checkpoint_rejects_modified_revision(self):
        self.prepare()
        path = v2._latest_path("nem-tu-van")
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["sha256"] = "0" * 64
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            v2.review("nem-tu-van")

    def test_visual_audit_never_claims_human_quality(self):
        self.prepare()
        report = v2.review("nem-tu-van")
        self.assertFalse(report["style_audit"]["aesthetic_quality_verified"])

    def test_local_image_reference_rejects_traversal(self):
        for src in ("assets/../secret.png", "assets/X.png", "assets/hero.svg"):
            with self.subTest(src=src), self.assertRaises(ValueError):
                web_assets.references(f'<img src="{src}">')

    def test_wrong_browser_channel_refused_before_model(self):
        with self.assertRaisesRegex(ValueError, "Invalid browser channel"):
            self.prepare(confirm_browser_run=True, browser_channel="invalid")
        self.assertEqual(self.calls, [])

    def test_no_model_called_during_review(self):
        self.prepare()
        with patch("agentforge.model.generate") as cloud:
            v2.review("nem-tu-van")
            cloud.assert_not_called()


if __name__ == "__main__":
    unittest.main()
