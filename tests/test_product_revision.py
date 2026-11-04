"""C8B: safe owner-gated revisions of an existing local static product."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder as builder
from agentforge import product_revision as revisions

BASE = '<!doctype html><html lang="vi"><head><style>body{color:black}</style></head><body><h1>Xin chào</h1></body></html>'
NEXT = '<!doctype html><html lang="vi"><head><style>body{color:blue}</style></head><body><h1>Xin chào</h1></body></html>'
REQUEST = "Change text color to blue; retain the original landing page structure."


class TestProductRevision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch.object(builder, "ROOT", self.root),
            patch.object(builder, "WORKSPACE", self.root / "workspace"),
            patch.object(builder, "PRODUCTS", self.root / "workspace" / "products"),
            patch.object(builder, "PROPOSALS", self.root / "data" / "company" / "product_builder" / "proposals"),
        ]
        for p in self.patches:
            p.start()
        self.path = builder.PRODUCTS / "shop-landing" / "index.html"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(BASE, encoding="utf-8")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def proposal(self, *, content=NEXT):
        with patch("agentforge.model.generate", return_value=content) as model:
            doc = revisions.propose("shop-landing", REQUEST)
            model.assert_called_once()
            self.assertEqual(model.call_args.kwargs, {"worker_id": "product_builder"})
        return doc

    def apply(self, proposal):
        return revisions.apply(proposal["revision_id"], confirm_write=True,
                               sha256=proposal["sha256"])

    def test_propose_keeps_existing_source_unchanged(self):
        before = self.path.read_bytes()
        result = self.proposal()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(Path(result["proposal_path"]).is_file())
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "backups").exists())
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "applied").exists())

    def test_proposal_contains_correct_original_hash(self):
        result = self.proposal()
        self.assertEqual(result["base_sha256"], revisions._hash(BASE.encode("utf-8")))
        doc = json.loads(Path(result["proposal_path"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["files"], [{"path": "index.html", "content": NEXT}])
        self.assertFalse(doc["execution_authorized"])

    def test_inspect_shows_current_and_sha_without_writing(self):
        prop = self.proposal()
        info = revisions.inspect(prop["revision_id"])
        self.assertEqual(info["sha256"], prop["sha256"])
        self.assertFalse(info["source_changed_since_proposal"])
        self.assertEqual(info["status"], "PROPOSED_NOT_APPLIED")
        self.assertEqual(self.path.read_text(encoding="utf-8"), BASE)

    def test_diff_is_read_only(self):
        prop = self.proposal()
        result = revisions.diff(prop["revision_id"])
        self.assertIn("-<!doctype html>", result)
        self.assertIn("+<!doctype html>", result)
        self.assertIn("body{color:blue}", result)
        self.assertEqual(self.path.read_text(encoding="utf-8"), BASE)

    def test_apply_requires_explicit_confirmation(self):
        prop = self.proposal()
        with self.assertRaises(PermissionError):
            revisions.apply(prop["revision_id"], sha256=prop["sha256"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), BASE)

    def test_apply_requires_exact_digest(self):
        prop = self.proposal()
        with self.assertRaises(PermissionError):
            revisions.apply(prop["revision_id"], confirm_write=True, sha256="0" * 64)
        self.assertEqual(self.path.read_text(encoding="utf-8"), BASE)

    def test_apply_creates_verified_backup_and_receipt(self):
        prop = self.proposal()
        result = self.apply(prop)
        self.assertEqual(result["status"], "FILES_REVISED_NOT_EXECUTED")
        self.assertEqual(self.path.read_text(encoding="utf-8"), NEXT)
        backup = Path(result["backup_path"])
        self.assertEqual(backup.read_text(encoding="utf-8"), BASE)
        _, receipt_path = revisions._paths(prop["revision_id"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["base_sha256"], prop["base_sha256"])
        self.assertFalse(receipt["deployment_authorized"])
        self.assertFalse(result["execution_authorized"])

    def test_cannot_apply_twice(self):
        prop = self.proposal()
        result = self.apply(prop)
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.apply(prop)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(Path(result["backup_path"]).read_bytes(), BASE.encode("utf-8"))

    def test_original_changes_after_proposal_prevent_write(self):
        prop = self.proposal()
        self.path.write_text(BASE.replace("black", "red"), encoding="utf-8")
        self.assertTrue(revisions.inspect(prop["revision_id"])["source_changed_since_proposal"])
        with self.assertRaisesRegex(RuntimeError, "STALE_REVISION"):
            self.apply(prop)
        self.assertIn("red", self.path.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "backups").exists())

    def test_diff_refuses_stale_source(self):
        prop = self.proposal()
        self.path.write_text(BASE.replace("black", "red"), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "STALE_REVISION"):
            revisions.diff(prop["revision_id"])

    def test_tampered_proposal_content_cannot_apply(self):
        prop = self.proposal()
        file = Path(prop["proposal_path"])
        doc = json.loads(file.read_text(encoding="utf-8"))
        doc["files"][0]["content"] = NEXT.replace("blue", "red")
        file.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.apply(prop)
        self.assertEqual(self.path.read_text(encoding="utf-8"), BASE)

    def test_forged_permission_flag_rejected(self):
        prop = self.proposal()
        file = Path(prop["proposal_path"])
        doc = json.loads(file.read_text(encoding="utf-8"))
        doc["execution_authorized"] = True
        file.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            revisions.inspect(prop["revision_id"])

    def test_extra_generated_file_rejected(self):
        prop = self.proposal()
        file = Path(prop["proposal_path"])
        doc = json.loads(file.read_text(encoding="utf-8"))
        doc["files"].append({"path": "app.js", "content": "alert(1)"})
        file.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.apply(prop)

    def test_proposal_id_path_traversal_rejected(self):
        for key in ("../outside", "C:\\Windows", "x" * 32, "" * 32, "0" * 33):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    revisions.inspect(key)

    def test_invalid_slug_rejected_before_model(self):
        with patch("agentforge.model.generate") as model:
            with self.assertRaises(ValueError):
                revisions.propose("../outside", REQUEST)
            model.assert_not_called()

    def test_missing_project_rejected_before_model(self):
        with patch("agentforge.model.generate") as model:
            with self.assertRaises(FileNotFoundError):
                revisions.propose("other-project", REQUEST)
            model.assert_not_called()

    def test_model_failure_no_revision_and_no_write(self):
        with patch("agentforge.model.generate", side_effect=RuntimeError("gateway down")) as model:
            with self.assertRaises(RuntimeError):
                revisions.propose("shop-landing", REQUEST)
            model.assert_called_once()
        self.assertEqual(self.path.read_text(encoding="utf-8"), BASE)
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "revisions").exists())

    def test_incomplete_html_rejected_without_proposal(self):
        with patch("agentforge.model.generate", return_value=NEXT[:80]):
            with self.assertRaises(ValueError):
                revisions.propose("shop-landing", REQUEST)
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "revisions").exists())

    def test_remote_network_html_rejected(self):
        malicious = NEXT.replace("</body>", '<script>fetch("https://example.org")</script></body>')
        with patch("agentforge.model.generate", return_value=malicious):
            with self.assertRaisesRegex(ValueError, "Disallowed"):
                revisions.propose("shop-landing", REQUEST)
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "revisions").exists())

    def test_no_change_is_not_a_revision(self):
        with patch("agentforge.model.generate", return_value=BASE):
            with self.assertRaisesRegex(ValueError, "unchanged"):
                revisions.propose("shop-landing", REQUEST)

    def test_source_modified_while_model_thinks_rejected(self):
        def modify(*args, **kwargs):
            self.path.write_text(BASE.replace("black", "green"), encoding="utf-8")
            return NEXT
        with self.assertRaisesRegex(RuntimeError, "Source changed during generation"):
            revisions.propose("shop-landing", REQUEST, model_client=modify)
        self.assertFalse((self.root / "data" / "company" / "product_builder" / "revisions").exists())

    def test_apply_does_not_start_shell_or_network(self):
        prop = self.proposal()
        with (patch("subprocess.run") as shell, patch("urllib.request.urlopen") as network):
            self.apply(prop)
            shell.assert_not_called()
            network.assert_not_called()

    def test_other_product_and_unrelated_files_untouched(self):
        other = builder.PRODUCTS / "other-product"
        other.mkdir()
        (other / "index.html").write_text("keep", encoding="utf-8")
        (self.path.parent / "styles.css").write_text("body { margin: 0 }", encoding="utf-8")
        prop = self.proposal()
        self.apply(prop)
        self.assertEqual((other / "index.html").read_text(encoding="utf-8"), "keep")
        self.assertEqual((self.path.parent / "styles.css").read_text(encoding="utf-8"), "body { margin: 0 }")

    def test_symlink_source_rejected(self):
        outside = self.root / "outside.html"
        outside.write_text(BASE, encoding="utf-8")
        self.path.unlink()
        try:
            self.path.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(PermissionError):
            revisions.propose("shop-landing", REQUEST)
        self.assertEqual(outside.read_text(encoding="utf-8"), BASE)

    def test_lock_prevents_concurrent_write(self):
        prop = self.proposal()
        lock = self.path.parent / ".agentforge-revision.lock"
        lock.write_text("already locked", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.apply(prop)
        self.assertEqual(self.path.read_text(encoding="utf-8"), BASE)
        self.assertEqual(lock.read_text(encoding="utf-8"), "already locked")

    def test_inspect_after_apply_reports_applied(self):
        prop = self.proposal()
        self.apply(prop)
        info = revisions.inspect(prop["revision_id"])
        self.assertEqual(info["status"], "ALREADY_APPLIED")
        self.assertTrue(info["source_changed_since_proposal"])

    def test_invalid_utf8_source_rejected(self):
        self.path.write_bytes(b"\xff\xfe")
        with self.assertRaises((ValueError, UnicodeError)):
            revisions.propose("shop-landing", REQUEST)

    def test_oversized_source_rejected(self):
        self.path.write_text(BASE + "x" * builder.MAX_FILE_BYTES, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exceeds size limit"):
            revisions.propose("shop-landing", REQUEST)


if __name__ == "__main__":
    unittest.main()
