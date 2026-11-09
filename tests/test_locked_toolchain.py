"""Locked scaffold and immutable legacy-source compatibility."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agentforge import webapp_developer as dev
from agentforge.domains.webapps import toolchain
from tests.test_webapp_developer_v42b import MODEL, BRIEF


class LockedToolchainTests(unittest.TestCase):
    def test_current_project_lock_matches_manifest(self):
        files = toolchain.project_files("locked-app")
        package, lock = (json.loads(files[n]) for n in ("package.json", "package-lock.json"))
        self.assertEqual(package["devDependencies"]["vite"], "7.3.7")
        esbuild = [entry["version"] for name, entry in lock["packages"].items()
                   if name.endswith("/esbuild")]
        self.assertTrue(esbuild)
        self.assertEqual(set(esbuild), {"0.28.1"})
        self.assertEqual(lock["packages"][""]["devDependencies"], package["devDependencies"])
        toolchain.require_current([{"path": k, "content": v} for k, v in files.items()])

    def test_historical_source_sha_remains_readable_but_toolchain_is_stale(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(dev, "PROPOSALS", Path(folder)), \
             patch.object(dev, "PROJECTS", Path(folder) / "projects"), \
             patch("agentforge.model.generate_json", return_value=MODEL):
            receipt = dev.propose("legacy-app", BRIEF)
            doc, path = dev._read_proposal(receipt["proposal_id"])
            doc["files"] = dev._compile(dev.validate_code(MODEL), "legacy-app", legacy=True)
            doc["sha256"] = dev._digest("legacy-app", BRIEF, doc["title"], doc["summary"], doc["files"])
            path.write_text(json.dumps(doc), encoding="utf-8")
            before = path.read_bytes()
            actual, _ = dev._read_proposal(doc["proposal_id"])
            self.assertEqual(actual["sha256"], doc["sha256"])
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "TOOLCHAIN_STALE"):
                toolchain.require_current(doc["files"])
