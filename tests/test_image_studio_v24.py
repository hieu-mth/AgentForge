"""V2.4 optional local ComfyUI image adapter regressions (mocked local HTTP)."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from agentforge import image_studio_v24 as lab
from agentforge import product_builder


class Response:
    status = 200
    def __init__(self, data):
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return None
    def read(self, count):
        return self.data[:count]


class ImageStudioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "images.sqlite3"
        self.products = self.root / "products"
        self.website = self.products / "nem-ngu"
        self.website.mkdir(parents=True)
        self.html = self.website / "index.html"
        self.html.write_text(
            '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Giới thiệu nệm ngủ</title></head><body><main>'
            '<h1>Nệm ngủ</h1><p>Liên hệ tư vấn nệm ngủ 0879547988.</p>'
            '</main></body></html>', encoding="utf-8")
        pp = patch.object(product_builder, "PRODUCTS", self.products)
        pp.start()
        self.addCleanup(pp.stop)
        active = patch("agentforge.ops_control.require_active", return_value=None)
        active.start()
        self.addCleanup(active.stop)
        self.provider_id = "11111111-2222-4333-8444-555555555555"
        output = io.BytesIO()
        Image.new("RGB", (768, 512), (180, 170, 160)).save(output, format="PNG")
        self.png = output.getvalue()
        self.requests = []
        self.job_id = None

    def endpoint(self, request, timeout):
        self.requests.append((request.get_method(), request.full_url, timeout))
        if request.full_url.endswith("/models/checkpoints"):
            return Response(["dream.safetensors"])
        if request.full_url.endswith("/prompt"):
            self.assertEqual("POST", request.get_method())
            data = json.loads(request.data)
            graph = data["prompt"]
            self.assertEqual("CheckpointLoaderSimple", graph["1"]["class_type"])
            self.assertEqual("KSampler", graph["5"]["class_type"])
            self.assertEqual("SaveImage", graph["7"]["class_type"])
            self.assertEqual(7, len(graph))
            self.assertEqual(20, graph["5"]["inputs"]["steps"])
            self.assertEqual(1, graph["4"]["inputs"]["batch_size"])
            self.job_id = graph["7"]["inputs"]["filename_prefix"].removeprefix("af_")
            return Response({"prompt_id": self.provider_id})
        if "/history/" in request.full_url:
            return Response({self.provider_id: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {"7": {"images": [{
                    "filename": "af_" + self.job_id + "_00001_.png",
                    "subfolder": "", "type": "output"
                }]}}
            }})
        if "/view?" in request.full_url:
            return Response(self.png)
        raise AssertionError("Unexpected HTTP route: " + request.full_url)

    def test_health_is_local_and_readonly(self):
        result = lab.health(opener=self.endpoint)
        self.assertEqual("READY", result["status"])
        self.assertFalse(result["generation_invoked"])
        self.assertEqual(["dream.safetensors"], result["checkpoints"])
        self.assertEqual("GET", self.requests[0][0])
        self.assertEqual(1, len(self.requests))

    def test_submitted_generated_imported_and_sha_attached(self):
        before = self.html.read_bytes()
        with self.assertRaises(PermissionError):
            lab.submit("nem-ngu", "A beautiful calm beige bedroom interior",
                       "dream.safetensors", db_path=self.db, opener=self.endpoint)
        result = lab.submit("nem-ngu", "A beautiful calm beige bedroom interior",
                            "dream.safetensors", confirm_generation=True,
                            db_path=self.db, opener=self.endpoint)
        self.assertEqual("SUBMITTED", result["status"])
        item_id = result["job_id"]
        self.assertFalse(result["external_publication"])
        rows = lab.report(db_path=self.db)["jobs"]
        self.assertEqual(1, len(rows))
        self.assertEqual(item_id, rows[0]["job_id"])
        with self.assertRaises(PermissionError):
            lab.collect(item_id, db_path=self.db, opener=self.endpoint)
        collected = lab.collect(item_id, confirm_import=True, db_path=self.db,
                                opener=self.endpoint)
        self.assertEqual("ASSET_READY", collected["status"])
        self.assertFalse(collected["published"])
        self.assertTrue((self.website / collected["asset"]).exists())
        self.assertEqual(hashlib.sha256(self.png).hexdigest(), collected["sha256"])
        with self.assertRaises(PermissionError):
            lab.collect(item_id, confirm_import=True, db_path=self.db,
                        opener=self.endpoint)
        with self.assertRaises(PermissionError):
            lab.attach(item_id, "0" * 64, hashlib.sha256(before).hexdigest(),
                       confirm_attach=True, db_path=self.db)
        receipt = lab.attach(item_id, collected["sha256"],
                             hashlib.sha256(before).hexdigest(),
                             confirm_attach=True, db_path=self.db)
        self.assertEqual("ATTACHED", receipt["status"])
        self.assertFalse(receipt["published"])
        self.assertIn("assets/af-ai-", self.html.read_text(encoding="utf-8"))
        self.assertTrue((self.website / receipt["backup"]).exists())
        self.assertEqual(before, (self.website / receipt["backup"]).read_bytes())

    def test_failed_submit_stays_claimed_no_retry(self):
        def fail_after_health(req, timeout):
            if req.full_url.endswith("/models/checkpoints"):
                return Response(["dream.safetensors"])
            raise TimeoutError("possible GPU generation executed")
        with self.assertRaises(TimeoutError):
            lab.submit("nem-ngu", "A beautiful calm beige bedroom interior",
                       "dream.safetensors", confirm_generation=True,
                       db_path=self.db, opener=fail_after_health)
        self.assertEqual("SUBMITTING", lab.report(db_path=self.db)["jobs"][0]["status"])

    def test_untrusted_image_path_is_never_downloaded(self):
        def evil(req, timeout):
            if "/history/" in req.full_url:
                return Response({self.provider_id: {
                    "status": {"status_str": "success", "completed": True},
                    "outputs": {"7": {"images": [
                        {"filename": "../secret.png", "subfolder": "", "type": "output"}]}
                    }}})
            if "/view?" in req.full_url:
                raise AssertionError("Untrusted output requested")
            return self.endpoint(req, timeout)
        result = lab.submit("nem-ngu", "A beautiful calm beige bedroom interior",
                            "dream.safetensors", confirm_generation=True,
                            db_path=self.db, opener=self.endpoint)
        with self.assertRaises(PermissionError):
            lab.collect(result["job_id"], confirm_import=True,
                        db_path=self.db, opener=evil)
        self.assertEqual("SUBMITTED", lab.report(db_path=self.db)["jobs"][0]["status"])


if __name__ == "__main__":
    unittest.main()
