"""Wave 7: signed export + browser QA security contracts (fixture only).

No browser/Docker is run in CI. Real Owner-pinned image acceptance is separate.
"""
import base64
import hashlib
import http.client
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentforge import webapp_builder as builder, webapp_developer as dev, brain_planner, brain_store
from agentforge.features.webapps import exporter, browser_qa, sandbox
from tests.test_webapp_developer_v42b import MODEL, BRIEF
from tests.test_webapp_revision_http_v41 import WebappRevisionHttpTests

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2b8AAAAASUVORK5CYII="
)
CHECKS = {name: True for name in browser_qa.CHECK_KEYS}
IMAGE = "sha256:" + "d" * 64


class Wave7ExportTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        for obj, attr, val in (
            (dev, "PROPOSALS", root / "react"),
            (dev, "PROJECTS", root / "projects"),
            (builder, "PROPOSALS", root / "marketplace"),
            (builder, "PROJECTS", root / "projects"),
        ):
            m = patch.object(obj, attr, val)
            m.start()
            self.addCleanup(m.stop)
        with patch("agentforge.model.generate_json", return_value=MODEL):
            self.source = dev.propose("react-original", BRIEF)

    def test_export_deterministic_and_no_data_workspace_writes(self):
        pid, sha = self.source["proposal_id"], self.source["sha256"]
        one, two = exporter.create_zip(pid, sha), exporter.create_zip(pid, sha)
        self.assertEqual(one["data"], two["data"])
        self.assertEqual(one["zip_sha256"], hashlib.sha256(one["data"]).hexdigest())
        self.assertEqual(exporter.verify_zip(one["data"], pid, sha)["status"],
                         "VERIFIED_SOURCE_ONLY")
        with zipfile.ZipFile(io.BytesIO(one["data"])) as z:
            names = z.namelist()
            self.assertIn("react-original/src/App.jsx", names)
            self.assertIn("react-original/package-lock.json", names)
            self.assertNotIn("react-original/.env", names)
            self.assertNotIn("react-original/node_modules", names)
            manifest = json.loads(z.read(exporter.MANIFEST_NAME))
            self.assertEqual(manifest["source_sha256"], sha)
            self.assertFalse(manifest["build_verified"])
            self.assertFalse(manifest["deployment_authorized"])
        self.assertFalse(dev.PROJECTS.exists())

    def test_invalid_sha_tampered_zip_and_traversal_guard(self):
        pid, sha = self.source["proposal_id"], self.source["sha256"]
        with self.assertRaises(PermissionError):
            exporter.create_zip(pid, "0" * 64)
        original = exporter.create_zip(pid, sha)["data"]
        edited = bytearray(original)
        edited[-20] ^= 0x01
        with self.assertRaises(PermissionError):
            exporter.verify_zip(bytes(edited), pid, sha)
        with self.assertRaises(PermissionError):
            exporter.verify_zip(b"not a zip", pid, sha)
        self.assertFalse(dev.PROJECTS.exists())

    def test_real_http_export_requires_session_and_exact_source_review(self):
        fixture = WebappRevisionHttpTests(
            "test_get_requires_login_and_allows_signed_source_review")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        from agentforge import webapp_developer
        # Use the fixture's authenticated server, but an independent signed AI draft.
        with patch.object(webapp_developer, "PROPOSALS", dev.PROPOSALS):
            pid = self.source["proposal_id"]
            path = "/api/webapps/" + pid + "/export"
            self.assertEqual(fixture.req("GET", path)[0], 401)
            fixture.login()
            self.assertEqual(fixture.req("GET", path)[0], 404)
            self.assertEqual(fixture.req("GET", "/api/webapps/" + pid)[0], 200)
            conn = http.client.HTTPConnection("127.0.0.1", fixture.server.server_port)
            conn.request("GET", path, headers={"Host": fixture.host,
                "Cookie": fixture.cookie})
            response = conn.getresponse()
            raw = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "application/zip")
            self.assertEqual(response.getheader("X-Source-SHA256"), self.source["sha256"])
            self.assertEqual(response.getheader("X-Archive-SHA256"),
                             hashlib.sha256(raw).hexdigest())
            self.assertIn("attachment;", response.getheader("Content-Disposition"))
            self.assertEqual(exporter.verify_zip(
                raw, pid, self.source["sha256"])["status"], "VERIFIED_SOURCE_ONLY")
            conn.close()


class Wave7BrowserQATests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        for obj, attr, val in (
            (dev, "PROPOSALS", root / "react"),
            (dev, "PROJECTS", root / "projects"),
            (builder, "PROPOSALS", root / "marketplace"),
            (builder, "PROJECTS", root / "projects"),
            (sandbox, "QA_STAGING", root / "staging"),
            (browser_qa, "REPORTS", root / "qa"),
        ):
            m = patch.object(obj, attr, val)
            m.start()
            self.addCleanup(m.stop)
        with patch("agentforge.model.generate_json", return_value=MODEL):
            self.source = dev.propose("react-original", BRIEF)

    def _run(self, value):
        payload = json.dumps(value, separators=(",", ":")) + "\n"
        commands = []
        def fake(args, **kwargs):
            commands.append((args, kwargs))
            if "image" in args:
                return SimpleNamespace(returncode=0, stdout="linux\n")
            self.assertIn("--network", args)
            self.assertEqual(args[args.index("--network")+1], "none")
            self.assertIn("--read-only", args)
            self.assertIn("--pull", args)
            self.assertEqual(args[args.index("--pull")+1], "never")
            self.assertIn("--cap-drop", args)
            self.assertEqual(args[args.index("--cap-drop")+1], "ALL")
            self.assertEqual(args[args.index("--user")+1], "10001:10001")
            self.assertIn(",readonly", args[args.index("--mount")+1])
            self.assertNotIn("ANTHROPIC_API_KEY", str(kwargs["env"]))
            self.assertIn("browser_runner.mjs", args[-1])
            return SimpleNamespace(returncode=0, stdout=payload)
        with patch.dict("os.environ", {
                "AGENTFORGE_BROWSER_QA_IMAGE": IMAGE,
                "ANTHROPIC_API_KEY": "private-test-token"}), \
             patch("shutil.which", return_value="docker"), \
             patch("subprocess.run", side_effect=fake):
            receipt = browser_qa.verify(self.source["proposal_id"],
                self.source["sha256"], confirm_external_run=True)
        self.assertEqual(len(commands), 2)
        self.assertEqual(list(sandbox.QA_STAGING.iterdir()), [])
        return receipt

    def test_requires_explicit_owner_consent_and_pinned_image(self):
        with patch("subprocess.run") as proc:
            with self.assertRaises(PermissionError):
                browser_qa.verify(self.source["proposal_id"], self.source["sha256"])
            with self.assertRaises(PermissionError):
                browser_qa.verify(self.source["proposal_id"], "0"*64,
                                  confirm_external_run=True)
            proc.assert_not_called()
        with patch.dict("os.environ", {"AGENTFORGE_BROWSER_QA_IMAGE": ""}), \
             patch("subprocess.run") as proc:
            with self.assertRaisesRegex(RuntimeError, "SANDBOX_UNAVAILABLE"):
                browser_qa.verify(self.source["proposal_id"], self.source["sha256"],
                                  confirm_external_run=True)
            proc.assert_not_called()
        self.assertFalse(browser_qa.REPORTS.exists())

    def test_smoke_saves_screenshots_and_report_without_native_execution(self):
        data = {"format": "agentforge.webapp.browser-smoke.v1",
                "status": "PASS_SMOKE_ONLY", "code": "BROWSER_SMOKE_ONLY",
                "checks": CHECKS, "desktop_png": base64.b64encode(PNG).decode(),
                "mobile_png": base64.b64encode(PNG).decode()}
        receipt = self._run(data)
        self.assertTrue(receipt["browser_smoke_verified"])
        self.assertFalse(receipt["functional_flows_verified"])
        self.assertTrue(receipt["build_verified"])
        self.assertFalse(dev.PROJECTS.exists())
        record = browser_qa.read_report(receipt["qa_report_id"],
                                        receipt["qa_report_sha"])
        self.assertEqual(record["source_sha256"], self.source["sha256"])
        self.assertEqual(browser_qa.image(
            receipt["qa_report_id"], receipt["qa_report_sha"], "desktop.png"), PNG)
        fp = browser_qa.REPORTS / receipt["qa_report_id"] / "desktop.png"
        fp.write_bytes(b"tampered screenshot")
        with self.assertRaises(PermissionError):
            browser_qa.read_report(receipt["qa_report_id"], receipt["qa_report_sha"])

    def test_build_failure_returns_bounded_fail_not_false_pass(self):
        data = {"format": "agentforge.webapp.browser-smoke.v1",
                "status": "FAIL", "code": "VITE_BUILD_FAILED"}
        result = self._run(data)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["build_verified"])
        self.assertFalse(result["browser_smoke_verified"])
        self.assertEqual(result["screenshots"], {})
        self.assertFalse(result["security_verified"])

    def test_forged_smoke_output_is_rejected(self):
        data = {"format": "agentforge.webapp.browser-smoke.v1",
                "status": "PASS_SMOKE_ONLY", "code": "BROWSER_SMOKE_ONLY",
                "checks": CHECKS, "desktop_png": "notbase64", "mobile_png": "alsoinvalid"}
        with self.assertRaisesRegex(ValueError, "BROWSER_QA_INVALID_SCREENSHOT"):
            self._run(data)
        self.assertFalse(browser_qa.REPORTS.exists())
        other = dict(data, desktop_png=base64.b64encode(PNG).decode(),
                     mobile_png=base64.b64encode(PNG).decode(),
                     checks={**CHECKS, "no_page_errors": False})
        with self.assertRaisesRegex(ValueError, "BROWSER_QA_INVALID_CHECKS"):
            self._run(other)

    def test_owner_goal_has_separate_external_budget_and_zero_model_calls(self):
        inputs = {"proposal_id": self.source["proposal_id"],
                  "sha256": self.source["sha256"],
                  "confirm_external_run": True}
        with self.assertRaises(brain_store.BrainError):
            brain_planner.make_plan("webapp.browser_qa", inputs,
                                    max_external_runs=0)
        steps = brain_planner.make_plan("webapp.browser_qa", inputs,
                                        max_external_runs=1)
        self.assertEqual([x["skill_id"] for x in steps], ["webapp.browser_qa"])
        self.assertEqual(steps[0]["estimated_model_calls"], 0)
        self.assertTrue(steps[0]["external_process"])
