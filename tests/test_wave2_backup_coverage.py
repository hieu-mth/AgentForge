"""Wave 2: persistent-state coverage and non-destructive restore contracts.

All files, databases and receipts are synthetic temp fixtures. Never touches
Owner data, calls external services or runs generated artifacts.
"""
import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from agentforge import ops_backup


class BackupCoverageWave2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data" / "company"
        self.workspace = self.root / "workspace"
        self.output = self.workspace / "backups"
        self.patches = [
            patch.object(ops_backup, "ROOT", self.root),
            patch.object(ops_backup, "DATA_DIR", self.data),
            patch.object(ops_backup, "WORKSPACE", self.workspace),
            patch.object(ops_backup, "OUT", self.output),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def put(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def db(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE state (name TEXT)")
            db.execute("INSERT INTO state VALUES (?)", (value,))
        return path

    def test_full_backup_captures_nested_state_all_known_feature_scopes(self):
        self.db("data/company/s1_tasks.sqlite3", "tasks")
        self.db("data/film_studio/motion.sqlite3", "motion")
        self.db("data/checkpoints.sqlite", "LangGraph")
        self.db("data/tool_integration.sqlite", "tool graph")
        payload = b"generated artifact linked by receipt"
        sha = hashlib.sha256(payload).hexdigest()
        items = {
            "data/company/product_builder/proposals/site.json": b'{"proposal_id":"site"}',
            "data/company/webapp_developer/proposals/react.json": b'{"proposal_id":"react"}',
            "data/company/customer_validation/records/buyer.json": b'{"status":"reviewed"}',
            "data/company/ops_control.json": b'{"mode":"PAUSED"}',
            "data/research/snapshot.json": b'{"sources":[]}',
            "data/backups/agentforge/retention-receipt.json": b'{"backup":"local"}',
            "workspace/products/site/index.html": b"<html>persisted</html>",
            "workspace/products/site/assets/hero.png": payload,
            "workspace/media/demo/video.mp4": b"fixture video",
            "workspace/growth/campaign.json": b'{"leads":1}',
            "workspace/webapps/react/src/App.jsx": b"export default function App(){}",
            "workspace/visuals/job.png": payload,
            "workspace/films/film/episode.mp4": b"episode fixture",
            "workspace/webapp-browser-qa/report/desktop.png": b"png fixture",
            "workspace/media_inputs/original.png": b"owner input",
            "workspace/analytics/inbox/campaign.csv": b"clicks\n1\n",
            "workspace/.quarantine/quarantined/receipt.json": b'{"sha":"verified"}',
        }
        for name, body in items.items():
            self.put(name, body)
        self.put("workspace/backups/previous.zip", b"do not recursively back up")
        self.put("workspace/.webapp-qa-staging/tmp/source.txt", b"ephemeral")
        self.put("data/company/s1_tasks.sqlite3-wal", b"ignore WAL sidecar")
        self.put("data/company/ops_daemon.lock", b"process lock")

        created = ops_backup.create(include_workspace=True, confirm_backup=True)
        self.assertEqual(created["coverage_status"], "KNOWN_SCOPES_COVERED")
        archive = Path(created["archive"])
        with zipfile.ZipFile(archive) as z:
            manifest = json.loads(z.read("manifest.json"))
            self.assertEqual(manifest["schema"], 2)
            self.assertEqual(manifest["coverage"]["level"], "KNOWN_SCOPES_COVERED")
            self.assertEqual(set(manifest["coverage"]["included_scopes"]),
                             set(ops_backup.FULL_SCOPES))
            self.assertFalse(manifest["coverage"]["cross_database_atomic"])
            self.assertFalse(manifest["coverage"]["reference_integrity_certified"])
            names = set(z.namelist())
        expected = set(items) | {
            "data/company/s1_tasks.sqlite3",
            "data/film_studio/motion.sqlite3",
            "data/checkpoints.sqlite", "data/tool_integration.sqlite",
            "manifest.json",
        }
        self.assertEqual(names, expected)
        self.assertEqual(created["files"], len(expected) - 1)
        self.assertEqual(ops_backup.verify(archive)["coverage_status"],
                         "KNOWN_SCOPES_COVERED")

        staged = self.root / "staged-review"
        outcome = ops_backup.stage_restore(archive, staged, confirm_restore=True)
        self.assertEqual(outcome["coverage_status"], "KNOWN_SCOPES_COVERED")
        self.assertFalse(outcome["active_databases_overwritten"])
        self.assertTrue(outcome["manual_owner_inspection_required"])
        self.assertFalse(outcome["reference_integrity_certified"])
        for relative, expected_data in items.items():
            self.assertEqual((staged / relative).read_bytes(), expected_data)
        self.assertEqual(hashlib.sha256(
            (staged / "workspace/products/site/assets/hero.png").read_bytes()
        ).hexdigest(), sha)
        for relative, text in (
            ("data/company/s1_tasks.sqlite3", "tasks"),
            ("data/film_studio/motion.sqlite3", "motion"),
            ("data/checkpoints.sqlite", "LangGraph"),
            ("data/tool_integration.sqlite", "tool graph"),
        ):
            with closing(sqlite3.connect(staged / relative)) as db:
                self.assertEqual(db.execute("SELECT name FROM state").fetchone()[0], text)
        self.assertFalse((staged / "workspace/backups").exists())
        self.assertFalse((staged / "workspace/.webapp-qa-staging").exists())

    def test_default_database_only_backup_cannot_claim_disaster_recovery(self):
        self.db("data/company/s1_tasks.sqlite3", "tasks")
        self.put("data/company/product_builder/proposals/site.json", b"valuable")
        self.put("workspace/products/site/index.html", b"valuable")
        created = ops_backup.create(confirm_backup=True)
        self.assertEqual(created["coverage_status"], "PARTIAL_DATABASE_ONLY")
        with zipfile.ZipFile(created["archive"]) as z:
            self.assertEqual(set(z.namelist()), {
                "data/company/s1_tasks.sqlite3", "manifest.json"})
        report = ops_backup.verify(created["archive"])
        self.assertEqual(report["coverage_status"], "PARTIAL_DATABASE_ONLY")

    def test_new_unrecognized_persistent_scope_is_flagged_not_silently_covered(self):
        self.db("data/company/s1_tasks.sqlite3", "tasks")
        self.put("data/next_feature/ledger.json", b"unrecognized data")
        self.put("workspace/unknown_feature/output.txt", b"unrecognized workspace")
        created = ops_backup.create(include_workspace=True, confirm_backup=True)
        self.assertEqual(created["coverage_status"], "REVIEW_REQUIRED")
        with zipfile.ZipFile(created["archive"]) as z:
            metadata = json.loads(z.read("manifest.json"))["coverage"]
        self.assertEqual(metadata["unrecognized_locations"],
                         ["data/next_feature", "workspace/unknown_feature"])
        self.assertEqual(ops_backup.verify(created["archive"])["coverage_status"],
                         "REVIEW_REQUIRED")

    def test_legacy_schema1_archive_verifies_and_stages_as_unattested(self):
        raw = b"<html>legacy</html>"
        doc = {
            "schema": 1,
            "contents": [{"path": "workspace/products/old/index.html",
                          "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                          "sqlite": False}],
        }
        path = self.root / "agentforge-20261110T000000Z-aabbccdd.zip"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(doc))
            z.writestr("workspace/products/old/index.html", raw)
        self.assertEqual(ops_backup.verify(path)["coverage_status"], "LEGACY_UNATTESTED")
        stage = self.root / "legacy-staging"
        result = ops_backup.stage_restore(path, stage, confirm_restore=True)
        self.assertEqual(result["coverage_status"], "LEGACY_UNATTESTED")
        self.assertEqual((stage / "workspace/products/old/index.html").read_bytes(), raw)

    def test_forged_coverage_and_unallowlisted_entry_are_refused(self):
        self.db("data/company/s1_tasks.sqlite3", "tasks")
        created = ops_backup.create(include_workspace=True, confirm_backup=True)
        archive = Path(created["archive"])
        with zipfile.ZipFile(archive) as z:
            content = {name: z.read(name) for name in z.namelist()}
        tampered = json.loads(content["manifest.json"])
        tampered["coverage"]["included_scopes"] = ["data/company"]
        content["manifest.json"] = json.dumps(tampered).encode()
        with zipfile.ZipFile(archive, "w") as z:
            for name, raw in content.items():
                z.writestr(name, raw)
        with self.assertRaisesRegex(ops_backup.BackupError, "coverage"):
            ops_backup.verify(archive)
        self.assertFalse((self.root / "unsafe-stage").exists())

    def test_oversized_full_snapshot_does_not_leave_partial_archive(self):
        self.db("data/company/s1_tasks.sqlite3", "tasks")
        self.put("workspace/visuals/big.png", b"x" * 300)
        with patch.object(ops_backup, "MAX_FILE", 250):
            with self.assertRaisesRegex(ops_backup.BackupError,
                                        "per-file|250 MB"):
                ops_backup.create(include_workspace=True, confirm_backup=True)
        self.assertFalse(list(self.output.glob("*.zip")))


if __name__ == "__main__":
    unittest.main()
