"""AI Builder V1: model proposals are untrusted until owner-accepted write."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder as b


class TestProductBuilder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(b, "ROOT", self.root),
            patch.object(b, "WORKSPACE", self.root / "workspace"),
            patch.object(b, "PRODUCTS", self.root / "workspace" / "products"),
            patch.object(b, "PROPOSALS", self.root / "data" / "company" / "product_builder" / "proposals"),
        ]
        for obj in self.patches:
            obj.start()
        self.slug = "shop-mvp"
        self.brief = "Create a clean offline landing page for a small shop."
        self.model_result = {
            "summary": "Offline product demo with a clear landing page",
            "files": [
                {"path": "index.html", "content": '<!doctype html><html lang="vi"><head><link rel="stylesheet" href="styles.css"></head><body><h1>Hello</h1><script src="app.js"></script></body></html>'},
                {"path": "styles.css", "content": "body { font-family: sans-serif; }"},
                {"path": "app.js", "content": "document.querySelector('h1').textContent = 'Hello';"},
            ],
        }

    def tearDown(self):
        for obj in reversed(self.patches):
            obj.stop()
        self.temp.cleanup()

    def proposal(self):
        def fake(prompt, schema, *, worker_id):
            self.assertEqual(worker_id, "product_builder")
            self.assertIn(self.brief, prompt)
            self.assertEqual(schema["properties"]["files"]["maxItems"], 4)
            return self.model_result
        return b.propose(self.slug, self.brief, model_client=fake)

    def test_propose_writes_plan_only(self):
        obj = self.proposal()
        self.assertFalse(b.PRODUCTS.exists())
        data = json.loads(Path(obj["proposal_path"]).read_text())
        self.assertEqual(data["status"], "PROPOSED_NOT_APPLIED")
        self.assertFalse(data["execution_authorized"])
        self.assertEqual(len(data["files"]), 3)

    def test_inspect_hash_and_files(self):
        obj = self.proposal()
        info = b.inspect(obj["proposal_id"])
        self.assertEqual(info["sha256"], obj["sha256"])
        self.assertEqual(sorted(x["path"] for x in info["files"]), sorted(obj["files"]))
        self.assertFalse(b.PRODUCTS.exists())

    def test_apply_requires_explicit_approval(self):
        obj = self.proposal()
        with self.assertRaises(PermissionError):
            b.apply(obj["proposal_id"], sha256=obj["sha256"])
        self.assertFalse(b.PRODUCTS.exists())

    def test_apply_requires_exact_digest(self):
        obj = self.proposal()
        with self.assertRaises(PermissionError):
            b.apply(obj["proposal_id"], confirm_write=True, sha256="0" * 64)
        self.assertFalse(b.PRODUCTS.exists())

    def test_apply_writes_only_expected_files(self):
        obj = self.proposal()
        done = b.apply(obj["proposal_id"], confirm_write=True, sha256=obj["sha256"])
        self.assertEqual(done["status"], "FILES_WRITTEN_NOT_EXECUTED")
        path = Path(done["project_path"])
        self.assertEqual(sorted(p.name for p in path.iterdir()), sorted(obj["files"]))
        self.assertFalse(done["execution_authorized"])
        self.assertEqual((path / "app.js").read_text(), self.model_result["files"][2]["content"])

    def test_duplicate_apply_never_overwrites(self):
        obj = self.proposal()
        b.apply(obj["proposal_id"], confirm_write=True, sha256=obj["sha256"])
        path = b.PRODUCTS / self.slug / "index.html"
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            b.apply(obj["proposal_id"], confirm_write=True, sha256=obj["sha256"])
        self.assertEqual(path.read_bytes(), before)

    def test_other_project_cannot_be_modified(self):
        other = b.PRODUCTS / "other-mvp"
        other.mkdir(parents=True)
        (other / "index.html").write_text("old", encoding="utf-8")
        obj = self.proposal()
        b.apply(obj["proposal_id"], confirm_write=True, sha256=obj["sha256"])
        self.assertEqual((other / "index.html").read_text(), "old")

    def test_unsafe_project_slug_rejected_before_model(self):
        for slug in ("../outside", "C:windows", "\\\\server", "CON", "con", "abc/def", "a", "a_foo"):
            with self.subTest(slug=slug):
                with self.assertRaises(ValueError):
                    b.propose(slug, self.brief, model_client=lambda *a, **kw: self.fail("model called"))

    def test_unsafe_generated_filename_rejected(self):
        for name in ("../evil.txt", "C:\\evil.txt", "data.json", "assets/app.js", "INDEX.HTML"):
            self.model_result["files"][1]["path"] = name
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.proposal()
        self.assertFalse(b.PROPOSALS.exists())

    def test_duplicate_output_file_rejected(self):
        self.model_result["files"][1]["path"] = "index.html"
        with self.assertRaises(ValueError):
            self.proposal()

    def test_missing_index_rejected(self):
        self.model_result["files"] = [{"path": "README.md", "content": "One project readme"}]
        with self.assertRaises(ValueError):
            self.proposal()

    def test_invalid_output_shape_rejected(self):
        self.model_result["extra"] = "hallucination"
        with self.assertRaises(ValueError):
            self.proposal()

    def test_oversized_file_rejected(self):
        self.model_result["files"][0]["content"] = "x" * (b.MAX_FILE_BYTES + 1)
        with self.assertRaises(ValueError):
            self.proposal()

    def test_remote_html_url_rejected(self):
        for src in ("https://somewhere.invalid/a.js", "//elsewhere.invalid/x.js", "data:text/javascript,alert(1)"):
            self.model_result["files"][0]["content"] = f'<script src="{src}"></script>'
            with self.subTest(src=src):
                with self.assertRaises(ValueError):
                    self.proposal()

    def test_unapproved_script_source_rejected(self):
        self.model_result["files"][0]["content"] = '<script src="../evil.js"></script>'
        with self.assertRaises(ValueError):
            self.proposal()

    def test_network_js_rejected(self):
        self.model_result["files"][2]["content"] = "fetch('/api/send')"
        with self.assertRaises(ValueError):
            self.proposal()

    def test_corrupted_proposal_rejected(self):
        obj = self.proposal()
        file = Path(obj["proposal_path"])
        doc = json.loads(file.read_text())
        doc["files"][0]["content"] = "Changed after proposal creation"
        file.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(ValueError):
            b.apply(obj["proposal_id"], confirm_write=True, sha256=obj["sha256"])
        self.assertFalse(b.PRODUCTS.exists())

    def test_permission_forgery_rejected(self):
        obj = self.proposal()
        file = Path(obj["proposal_path"])
        doc = json.loads(file.read_text())
        doc["execution_authorized"] = True
        file.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            b.inspect(obj["proposal_id"])

    def test_proposal_id_path_escape_rejected(self):
        for proposal_id in ("../other", "", "0" * 33, "x" * 32):
            with self.assertRaises(ValueError):
                b.inspect(proposal_id)

    def test_model_failure_creates_no_proposal(self):
        def broken(*args, **kwargs):
            raise RuntimeError("Offline model unavailable")
        with self.assertRaises(RuntimeError):
            b.propose(self.slug, self.brief, model_client=broken)
        self.assertFalse(b.PROPOSALS.exists())

    def test_no_network_or_subprocess_on_apply(self):
        obj = self.proposal()
        with (patch("subprocess.run") as shell, patch("urllib.request.urlopen") as net):
            b.apply(obj["proposal_id"], confirm_write=True, sha256=obj["sha256"])
            shell.assert_not_called()
            net.assert_not_called()

    def test_symlink_product_directory_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        b.WORKSPACE.mkdir()
        try:
            b.PRODUCTS.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not available")
        with self.assertRaises(PermissionError):
            self.proposal()
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
