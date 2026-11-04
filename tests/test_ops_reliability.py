"""Local backup/doctor acceptance. Never touch project or personal databases."""
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from agentforge import ops_backup, ops_doctor, brain_store, ops_daemon


class TestOperationsRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "data" / "company"
        self.products = self.root / "workspace" / "products"
        self.media = self.root / "workspace" / "media"
        self.backups = self.root / "workspace" / "backups"
        self.data.mkdir(parents=True)
        self.products.mkdir(parents=True)
        self.sqlite_path = self.data / "s1_tasks.sqlite3"
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute("CREATE TABLE check_value(id INTEGER PRIMARY KEY, text TEXT)")
            conn.execute("INSERT INTO check_value(text) VALUES('already-stored')")
        (self.products / "index.html").write_text("<h1>Existing content</h1>",
                                                  encoding="utf-8")
        self.patches = [
            patch.object(ops_backup, "ROOT", self.root),
            patch.object(ops_backup, "DATA_DIR", self.data),
            patch.object(ops_backup, "WORKSPACE", self.root / "workspace"),
            patch.object(ops_backup, "OUT", self.backups),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_confirmation_required_no_backup_created(self):
        with self.assertRaises(PermissionError):
            ops_backup.create()
        self.assertFalse(self.backups.exists())

    def test_live_sqlite_snapshot_and_restore_only_to_new_staging(self):
        # WAL mode, live writer: backup should see committed data without touching DB.
        with sqlite3.connect(self.sqlite_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT INTO check_value(text) VALUES('committed')")
        created = ops_backup.create(include_workspace=True, confirm_backup=True)
        self.assertEqual(created["status"], "CREATED_AND_VERIFIED")
        self.assertEqual(created["files"], 2)
        archive = Path(created["archive"])
        self.assertTrue(archive.exists())
        self.assertTrue(created["unencrypted"])
        self.assertEqual(ops_backup.verify(archive)["status"], "PASS")
        original = self.sqlite_path.read_bytes()
        staged = self.root / "restore-review"
        with self.assertRaises(PermissionError):
            ops_backup.stage_restore(archive, staged)
        self.assertFalse(staged.exists())
        result = ops_backup.stage_restore(
            archive, staged, confirm_restore=True)
        self.assertEqual(result["status"], "RESTORED_TO_STAGING_ONLY")
        self.assertFalse(result["active_databases_overwritten"])
        with sqlite3.connect(staged / "data/company/s1_tasks.sqlite3") as db:
            rows = db.execute("SELECT text FROM check_value ORDER BY id").fetchall()
        self.assertEqual(rows, [("already-stored",), ("committed",)])
        self.assertEqual(
            (staged / "workspace/products/index.html").read_text(encoding="utf-8"),
            "<h1>Existing content</h1>")
        self.assertEqual(self.sqlite_path.read_bytes(), original)
        with self.assertRaisesRegex(ops_backup.BackupError, "must not exist"):
            ops_backup.stage_restore(archive, staged, confirm_restore=True)

    def test_backup_without_workspace_does_not_copy_product_files(self):
        archive = ops_backup.create(confirm_backup=True)["archive"]
        with zipfile.ZipFile(archive) as zf:
            self.assertEqual(set(zf.namelist()), {
                "data/company/s1_tasks.sqlite3", "manifest.json"})
        self.assertEqual(ops_backup.verify(archive)["files"], 1)

    def test_missing_sources_refused_without_empty_zip(self):
        self.sqlite_path.unlink()
        with self.assertRaisesRegex(ops_backup.BackupError, "No local data"):
            ops_backup.create(confirm_backup=True)
        self.assertFalse(self.backups.exists())

    def test_tampering_detected_even_with_zip_repacked(self):
        path = Path(ops_backup.create(confirm_backup=True)["archive"])
        with zipfile.ZipFile(path) as zf:
            raw = {name: zf.read(name) for name in zf.namelist()}
        raw["data/company/s1_tasks.sqlite3"] = b"malicious-bytes"
        with zipfile.ZipFile(path, "w") as zf:
            for name, data in raw.items():
                zf.writestr(name, data)
        with self.assertRaisesRegex(ops_backup.BackupError, "lengths differ|checksum"):
            ops_backup.verify(path)
        self.assertFalse((self.root / "restore").exists())

    def test_zip_slip_is_blocked_by_manifest(self):
        path = Path(ops_backup.create(confirm_backup=True)["archive"])
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        manifest["contents"][0]["path"] = "../secrets.txt"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("../secrets.txt", b"bad")
        with self.assertRaisesRegex(ops_backup.BackupError, "Unsafe"):
            ops_backup.verify(path)

    def test_symlinked_source_disallowed(self):
        link = self.products / "linked.html"
        outside = self.root / "outside.html"
        outside.write_text("outside", encoding="utf-8")
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Windows symlinks require developer mode")
        with self.assertRaisesRegex(ops_backup.BackupError, "Symlink"):
            ops_backup.create(confirm_backup=True, include_workspace=True)

    def test_doctor_reports_missing_backup_and_running_tasks_without_recovery(self):
        with patch.object(ops_doctor.skill_registry, "load_registry",
                          return_value={"web.quality_check": {}}):
            with patch.object(ops_doctor.ops_daemon, "read_heartbeat",
                              return_value={"status": "NOT_RUNNING", "fresh": False}):
                with patch.object(ops_doctor.task_history, "list_tasks",
                                  return_value=[{"status": "RUNNING"}]):
                    with patch.object(ops_doctor.brain_store, "list_goals",
                                      return_value=[{"status": "RUNNING"}]):
                        result = ops_doctor.inspect(
                            paths={"test": self.sqlite_path},
                            backup_dir=self.backups, task_db=self.sqlite_path,
                            brain_db=self.data / "goals.sqlite3")
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["running_tasks"], 1)
        self.assertEqual(result["running_goals"], 1)
        self.assertEqual(result["backup_count"], 0)
        self.assertFalse(result["automatic_recovery_performed"])
        with sqlite3.connect(self.sqlite_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM check_value").fetchone()[0], 1)

    def test_doctor_detects_corrupt_sqlite_and_reports_failure_without_write(self):
        damaged = self.data / "corrupt.sqlite3"
        damaged.write_bytes(b"not a sqlite database")
        with patch.object(ops_doctor.skill_registry, "load_registry",
                          return_value={"web.quality_check": {}}):
            with patch.object(ops_doctor.ops_daemon, "read_heartbeat",
                              return_value={"status": "NOT_RUNNING", "fresh": False}):
                with patch.object(ops_doctor.task_history, "list_tasks",
                                  return_value=[]):
                    with patch.object(ops_doctor.brain_store, "list_goals",
                                      return_value=[]):
                        out = ops_doctor.inspect(
                            paths={"corrupt": damaged},
                            backup_dir=self.backups)
        self.assertEqual(out["status"], "FAIL")
        self.assertIn("sqlite_integrity", [f["rule"] for f in out["findings"]])
        self.assertEqual(damaged.read_bytes(), b"not a sqlite database")


if __name__ == "__main__":
    unittest.main()
