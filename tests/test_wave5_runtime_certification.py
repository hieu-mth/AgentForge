"""Wave 5 runtime certification: no false readiness and explicit side-effect gates.

All provider and Docker probes are local fixtures/mocks; the actual FFmpeg
encode/decode probe is run separately in Windows CI with an isolated temp file.
"""
import hashlib
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from agentforge.ops import runtime_certification as rc


class LoopbackHttpFixture(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(("GET", self.path))
        if self.path == "/api/tags":
            self._send({"models": [{"name": "test-local:latest"}]})
        elif self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/dashboard/")
            self.end_headers()
        else:
            self.send_response(302)
            self.send_header("Location", "https://outside.example/token")
            self.end_headers()

    def do_POST(self):
        self.server.requests.append(("POST", self.path))
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size))
        self.server.payloads.append(body)
        self._send({"done": True, "message": {"content": "READY"},
                    "eval_count": 2, "prompt_eval_count": 10})

    def _send(self, data):
        b = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *_):
        return


class LocalProbeTests(unittest.TestCase):
    def setUp(self):
        server = HTTPServer(("127.0.0.1", 0), LoopbackHttpFixture)
        self.server = server
        server.requests, server.payloads = [], []
        self.port = server.server_port
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()
        def stop():
            server.shutdown()
            self.thread.join(timeout=3)
            server.server_close()
        self.addCleanup(stop)
        self.profile = ("127.0.0.1", self.port, "test-local:latest")

    def test_loopback_tag_probe_is_no_inference_and_no_redirect(self):
        with patch.object(rc, "_ollama_profile", return_value=self.profile):
            result = rc._ollama_preflight("local_primary")
        self.assertEqual(result["status"], "READY_FOR_INFERENCE")
        self.assertFalse(result["inference_invoked"])
        self.assertEqual(self.server.requests, [("GET", "/api/tags")])
        with self.assertRaisesRegex(ValueError, "Unapproved local route"):
            rc._http_json("127.0.0.1", self.port, "/unexpected")
        self.assertEqual(self.server.requests, [("GET", "/api/tags")])
        for url in ("https://outside.example", "http://169.254.1.1:11434",
                    "http://127.0.0.1:11434@evil.example"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                rc._local_endpoint(url)

    def test_inference_runs_once_only_after_explicit_flag(self):
        with patch.object(rc, "_ollama_profile", return_value=self.profile):
            result = rc._ollama_inference("local_primary")
        self.assertEqual(result["status"], "PASS_RUNTIME")
        self.assertEqual(result["output_sha256"], hashlib.sha256(b"READY").hexdigest())
        self.assertNotIn("READY", json.dumps(result))
        self.assertEqual(self.server.requests, [("POST", "/api/chat")])
        self.assertEqual(len(self.server.payloads), 1)
        payload = self.server.payloads[0]
        self.assertEqual(payload["model"], "test-local:latest")
        self.assertEqual(payload["options"]["num_predict"], 32)
        self.assertFalse(payload["stream"])

    def test_invalid_routes_and_response_caps_fail_closed(self):
        with self.assertRaises(ValueError):
            rc._http_json("outside.example", 443, "/api/tags")
        with self.assertRaises(ValueError):
            rc._http_json("127.0.0.1", self.port, "/api/chat",
                          max_bytes=rc.MAX_TAGS_BYTES+1)
        with self.assertRaises(ValueError):
            rc._http_json("127.0.0.1", self.port, "/api/tags", max_bytes=20)
        self.assertEqual(self.server.requests, [("GET", "/api/tags")])


class CertificationGatesTests(unittest.TestCase):
    def _mock_preflight(self):
        return [
            patch.object(rc, "_ollama_preflight",
                         return_value={"status": "MODEL_NOT_INSTALLED"}),
            patch.object(rc, "_comfy_preflight",
                         return_value={"status": "UNAVAILABLE"}),
            patch.object(rc, "_ffmpeg_preflight",
                         return_value={"status": "UNAVAILABLE"}),
            patch.object(rc, "_docker_preflight",
                         return_value={"status": "QA_IMAGE_NOT_PINNED"}),
            patch.object(rc, "_dashboard_preflight",
                         return_value={"status": "UNAVAILABLE"}),
        ]

    def test_default_preflight_never_runs_runtime_writes_or_inference(self):
        guards = self._mock_preflight()
        for g in guards:
            g.start()
            self.addCleanup(g.stop)
        with patch.object(rc, "_ollama_inference") as llm, \
             patch.object(rc, "_ffmpeg_runtime") as ffmpeg, \
             patch.object(rc, "_docker_runtime") as docker, \
             patch.object(rc, "save_report") as writer:
            report = rc.inspect()
        for guard in (llm, ffmpeg, docker, writer):
            guard.assert_not_called()
        self.assertEqual(report["status"], "OWNER_RUNTIME_PENDING")
        self.assertFalse(report["production_go"])
        self.assertFalse(report["real_gpu_video_verified"])
        self.assertFalse(report["generated_app_browser_verified"])
        self.assertEqual(report["cloud_requests"], 0)
        self.assertEqual(report["gpu_jobs_submitted"], 0)
        self.assertEqual(len(report["report_sha256"]), 64)
        self.assertNotIn("ollama_inference", report["checks"])
        self.assertFalse(report["explicit_authorization"]["local_ollama_inference"])

    def test_opt_in_failure_is_not_mislabeled_as_certified(self):
        guards = self._mock_preflight()
        for g in guards:
            g.start()
            self.addCleanup(g.stop)
        with patch.object(rc, "_ollama_inference", side_effect=OSError("PRIVATE-SECRET")) as run:
            report = rc.inspect(run_ollama=True)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(report["status"], "OPTIONAL_PROBE_FAILED")
        self.assertEqual(report["checks"]["ollama_inference"], {"status": "UNAVAILABLE"})
        self.assertNotIn("PRIVATE-SECRET", json.dumps(report))
        self.assertFalse(report["production_go"])

    def test_opt_in_success_remains_owner_pending_other_unverified_scopes(self):
        guards = self._mock_preflight()
        for g in guards:
            g.start()
            self.addCleanup(g.stop)
        with patch.object(rc, "_ffmpeg_runtime",
                          return_value={"status": "PASS_RUNTIME"}) as run:
            report = rc.inspect(run_ffmpeg=True)
        run.assert_called_once()
        self.assertEqual(report["status"], "OWNER_RUNTIME_PENDING")
        self.assertEqual(report["checks"]["ffmpeg_encode_decode"]["status"], "PASS_RUNTIME")
        self.assertEqual(
            report["checks"]["film_motion_import_decode_owner_review"]["status"],
            "OWNER_RUNTIME_PENDING")

    def test_cli_approval_is_required_before_any_host_probe(self):
        for args in (
                ["--run-ollama"], ["--run-ffmpeg"], ["--run-docker"],
                ["--run-ollama", "--run-ffmpeg", "--confirm-local-exec"]):
            with self.subTest(args=args), patch.object(rc, "inspect") as inspect:
                with self.assertRaises(SystemExit) as error:
                    rc.main(args)
                self.assertEqual(error.exception.code, 2)
                inspect.assert_not_called()

    def test_save_receipt_requires_flag_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
                rc, "WORKSPACE_DIR", Path(temp)/"workspace"):
            report = {"evidence_id": "c" * 32, "format": rc.REPORT_FORMAT,
                      "report_sha256": "d" * 64}
            self.assertFalse((Path(temp)/"workspace").exists())
            dest = rc.save_report(report)
            self.assertTrue(dest.is_file())
            self.assertEqual(json.loads(dest.read_text()), report)
            with self.assertRaises(FileExistsError):
                rc.save_report(report)
            self.assertEqual(json.loads(dest.read_text()), report)

    def test_pinned_docker_run_is_offline_no_user_source(self):
        from agentforge.features.webapps import sandbox
        with patch.object(rc, "_docker_context", return_value=(
                "docker", "npipe:////./pipe/docker_engine", "sha256:"+"a"*64)), \
             patch.object(sandbox, "_image_ready") as ready, \
             patch.object(rc.subprocess, "run", return_value=type(
                 "Done", (), {"returncode": 0})()) as run:
            result = rc._docker_runtime()
        self.assertEqual(result["status"], "PASS_RUNTIME")
        self.assertFalse(result["browser_qa_verified"])
        self.assertFalse(result["source_executed"])
        self.assertTrue(result["pinned_image"])
        args = run.call_args.args[0]
        self.assertIn("--network", args)
        self.assertIn("none", args)
        self.assertIn("--read-only", args)
        self.assertIn("--pull", args)
        self.assertIn("never", args)
        self.assertNotIn("--mount", args)
        ready.assert_called_once()


if __name__ == "__main__":
    unittest.main()
