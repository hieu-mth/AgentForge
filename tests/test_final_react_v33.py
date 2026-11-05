"""V3.3 final React owner navigation and retention API surface checks."""
import unittest
from pathlib import Path
from agentforge import paths

class FinalOwnerUIContract(unittest.TestCase):
    def test_react_has_retention_actions_and_no_permanent_purge(self):
        source=(paths.UI_DASHBOARD_DIR/"src"/"features"/"Retention.jsx").read_text(
            encoding="utf-8")
        for route in ("/api/retention/inventory","/api/retention/backups",
                      "/api/retention/inspect/","/api/retention/verify/",
                      "/api/retention/backup","/api/retention/quarantine",
                      "/api/retention/restore"):
            self.assertIn(route,source)
        for ack in ("BACKUP_ARTIFACT","QUARANTINE_ARTIFACT","RESTORE_ARTIFACT"):
            self.assertIn(ack,source)
        self.assertNotIn("/api/retention/purge",source)
        self.assertIn("PAUSED",source)
        self.assertIn("tree_sha256",source)

    def test_owner_navigation_and_session_controls(self):
        app=(paths.UI_DASHBOARD_DIR/"src"/"App.jsx").read_text(encoding="utf-8")
        grants=(paths.UI_DASHBOARD_DIR/"src"/"features"/"Workspace.jsx").read_text(
            encoding="utf-8")
        self.assertIn("Backups & Retention",app)
        self.assertIn("section==='retention'",app)
        self.assertIn("/api/logout",app)
        self.assertIn("workspace.read",grants)
        self.assertIn("workspace.write",grants)

if __name__=="__main__":
    unittest.main()
