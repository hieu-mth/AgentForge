"""M9 preflight: no network, process execution, owner data or credentials."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.ops import preflight


def make_root(root):
    for file in ("agentforge/__main__.py", "pyproject.toml",
                 "dashboard/package.json", "dashboard/dist/index.html",
                 "config/models.toml", "config/task_routes.toml"):
        path = root / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("sample", encoding="utf-8")
    (root / "workers").mkdir()


class M9PreflightTests(unittest.TestCase):
    def test_complete_local_layout_has_no_provider_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_root(root)
            found = []
            result = preflight.inspect(root=root, version=(3, 13, 1),
                                       which=lambda binary: found.append(binary) or "/bin/tool")
            self.assertEqual(result["status"], "READY_LOCAL_UNVERIFIED")
            self.assertEqual(len(found), 2)
            self.assertTrue(result["read_only"])
            self.assertFalse(result["network_called"])
            self.assertFalse(result["provider_models_tested"])
            self.assertFalse(result["installation_performed"])
            serialized = json.dumps(result)
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("/bin/tool", serialized)
            self.assertEqual(len(result["checks"]), 10)

    def test_missing_build_and_node_only_require_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_root(root)
            (root / "dashboard/dist/index.html").unlink()
            result = preflight.inspect(root=root, version=(3, 13, 2),
                                       which=lambda _: None)
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            self.assertEqual(next(x for x in result["checks"]
                                  if x["id"] == "dashboard_build")["status"], "NEEDS_SETUP")
            self.assertFalse((root / "dashboard/dist/index.html").exists())

    def test_unsupported_python_missing_config_and_links_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_root(root)
            (root / "config/task_routes.toml").unlink()
            blocked = preflight.inspect(root=root, version=(3, 12, 9),
                                        which=lambda _: "tool")
            self.assertEqual(blocked["status"], "BLOCKED")
            self.assertEqual(next(x for x in blocked["checks"]
                                  if x["id"] == "python")["status"], "BLOCKED")
            config = root / "config/models.toml"
            config.unlink()
            dest = root / "outside.toml"
            dest.write_text("unsafe", encoding="utf-8")
            try:
                config.symlink_to(dest)
            except (OSError, NotImplementedError):
                return
            self.assertEqual(preflight._path_status(root, "config/models.toml", "file"),
                             "BLOCKED")

    def test_no_subprocess_network_or_workspace_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_root(root)
            secret = root / "data" / "company" / "owner-secret.sqlite3"
            secret.parent.mkdir(parents=True)
            secret.write_text("secret-not-to-inspect", encoding="utf-8")
            with (patch("subprocess.run", side_effect=AssertionError("subprocess forbidden")),
                  patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden"))):
                result = preflight.inspect(root=root, version=(3, 13, 1),
                                           which=lambda _: None)
            self.assertNotIn("secret-not-to-inspect", json.dumps(result))
            self.assertEqual(secret.read_text(encoding="utf-8"), "secret-not-to-inspect")

    def test_cp1252_windows_cli_never_crashes_on_vietnamese_labels(self):
        payload = {"status": "READY_LOCAL_UNVERIFIED",
                   "checks": [{"detail": "Đã tìm thấy"}]}
        stream = io.BytesIO()
        writer = io.TextIOWrapper(stream, encoding="cp1252", write_through=True)
        with patch.object(preflight, "inspect", return_value=payload), \
             patch.object(sys, "stdout", writer), \
             patch.object(sys, "argv", ["preflight"]):
            preflight.main()
        self.assertEqual(json.loads(stream.getvalue().decode("ascii")), payload)

    def test_authenticated_get_route_still_needs_owner_session(self):
        import tests.test_webapp_revision_http_v41 as fixture
        test = fixture.WebappRevisionHttpTests(
            "test_get_requires_login_and_allows_signed_source_review")
        test.setUp()
        self.addCleanup(test.doCleanups)
        self.assertEqual(test.req("GET", "/api/ops/preflight")[0], 401)
        test.login()
        status, body, _ = test.req("GET", "/api/ops/preflight")
        self.assertEqual(status, 200)
        self.assertTrue(body["read_only"])
        self.assertFalse(body["provider_models_tested"])
        self.assertNotIn("api_key", json.dumps(body).lower())


if __name__ == "__main__":
    unittest.main()
