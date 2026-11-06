"""Local-state archival is opt-in and never erases customer data."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "archive_local_state.py"
SPEC = importlib.util.spec_from_file_location("agentforge_archive_state_test", MODULE)
reset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reset)


class LocalStateArchiveTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "AgentForge"
        self.root.mkdir()
        self.archive = Path(t.name) / "AgentForge-local-state-archives"
        self.p1 = patch.object(reset, "ROOT", self.root)
        self.p2 = patch.object(reset, "ARCHIVE_ROOT", self.archive)
        self.p1.start(); self.p2.start()
        self.addCleanup(self.p1.stop); self.addCleanup(self.p2.stop)

    def seed(self):
        for folder, name, raw in (
            ("data", "tasks.sqlite3", b"VERY_IMPORTANT_SQLITE"),
            ("workspace", "index.html", b"PAID_CUSTOMER_WEBSITE")):
            base = self.root / folder
            base.mkdir()
            (base / name).write_bytes(raw)

    def test_default_is_read_only_and_requires_explicit_stopped_confirmation(self):
        self.seed()
        before = reset.report()
        self.assertEqual("REPORT_ONLY", before["operation"])
        self.assertFalse(self.archive.exists())
        with self.assertRaises(PermissionError):
            reset.archive()
        with self.assertRaises(PermissionError):
            reset.archive(confirm_stopped=True, confirmation="DELETE_ALL")
        self.assertTrue((self.root / "data" / "tasks.sqlite3").exists())

    def test_archive_full_runtime_then_restore_exact_original(self):
        self.seed()
        saved = reset.archive(confirm_stopped=True, confirmation="ARCHIVE_LOCAL_STATE")
        self.assertEqual("ARCHIVED", saved["status"])
        self.assertFalse((self.root / "data").exists())
        self.assertFalse((self.root / "workspace").exists())
        self.assertEqual(0, saved["deleted_files"])
        snapshot = self.archive / saved["archive_id"]
        self.assertEqual(b"VERY_IMPORTANT_SQLITE",
                         (snapshot / "data" / "tasks.sqlite3").read_bytes())
        self.assertEqual(b"PAID_CUSTOMER_WEBSITE",
                         (snapshot / "workspace" / "index.html").read_bytes())
        self.assertEqual("ARCHIVED", json.loads(
            (snapshot / "manifest.json").read_text())["status"])
        with self.assertRaises(PermissionError):
            reset.restore(saved["archive_id"])
        restored = reset.restore(saved["archive_id"],
                                 confirm_stopped=True,
                                 confirmation="RESTORE_LOCAL_STATE")
        self.assertEqual(["data", "workspace"], restored["restored"])
        self.assertEqual(b"PAID_CUSTOMER_WEBSITE",
                         (self.root / "workspace" / "index.html").read_bytes())
        self.assertEqual(b"VERY_IMPORTANT_SQLITE",
                         (self.root / "data" / "tasks.sqlite3").read_bytes())

    def test_restore_refuses_to_override_new_state(self):
        self.seed()
        saved = reset.archive(confirm_stopped=True, confirmation="ARCHIVE_LOCAL_STATE")
        (self.root / "data").mkdir()
        (self.root / "data" / "current.sqlite3").write_bytes(b"NEW_TASKS")
        with self.assertRaises(FileExistsError):
            reset.restore(saved["archive_id"],
                          confirm_stopped=True, confirmation="RESTORE_LOCAL_STATE")
        self.assertEqual(b"NEW_TASKS",
                         (self.root / "data" / "current.sqlite3").read_bytes())
        self.assertTrue((self.archive / saved["archive_id"] / "data").exists())

    def test_empty_data_is_noop(self):
        self.assertEqual("ALREADY_EMPTY",reset.archive(
            confirm_stopped=True,confirmation="ARCHIVE_LOCAL_STATE")["status"])
        self.assertFalse(self.archive.exists())

    def test_invalid_archive_id_and_path_symlink_refused(self):
        with self.assertRaises(ValueError):
            reset.restore("../data",confirm_stopped=True,confirmation="RESTORE_LOCAL_STATE")
        self.seed()
        if hasattr(Path, "is_junction"):
            # Existing real path is always safe regardless of platform.
            self.assertFalse(reset._linked(self.root / "workspace"))
        alias = self.root / "linked"
        try: alias.symlink_to(self.root / "data", target_is_directory=True)
        except (OSError, NotImplementedError): return
        with self.assertRaises(PermissionError):
            reset._safe_chain(alias / "file.sqlite3")


if __name__ == "__main__":
    unittest.main()
