"""Pause/resume cannot implicitly launch a Film Studio job."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import ops_control


class OperationsPauseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "control.json"
        p = patch.object(ops_control, "STATE_FILE", self.state)
        p.start()
        self.addCleanup(p.stop)

    def test_missing_state_is_read_only_active(self):
        self.assertEqual(ops_control.read()["mode"], "ACTIVE")
        self.assertTrue(ops_control.require_active())
        self.assertFalse(self.state.exists())

    def test_explicit_pause_and_resume(self):
        with self.assertRaises(PermissionError):
            ops_control.set_mode("PAUSED")
        self.assertEqual(ops_control.set_mode("PAUSED", confirm=True)["mode"], "PAUSED")
        with self.assertRaisesRegex(PermissionError, "OPERATIONS_PAUSED"):
            ops_control.require_active()
        self.assertEqual(ops_control.set_mode("ACTIVE", confirm=True)["mode"], "ACTIVE")
        self.assertTrue(ops_control.require_active())

    def test_invalid_state_fails_closed(self):
        self.state.write_text("{bad", encoding="utf-8")
        self.assertEqual(ops_control.read()["mode"], "PAUSED")
        with self.assertRaises(PermissionError):
            ops_control.require_active()

    def test_invalid_mode_does_not_write(self):
        with self.assertRaises(PermissionError):
            ops_control.set_mode("STOP_ALL", confirm=True)
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
