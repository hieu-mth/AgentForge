"""Owner API guards for artifact snapshots, quarantine and restore."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from agentforge.control_center_v1 import _owner_action

class RetentionOwnerAPITests(unittest.TestCase):
    def setUp(self):
        self.server=SimpleNamespace()
        self.session={"inspected_artifacts":{("website","nem-ngu"):"a"*64},
                      "verified_artifact_backups":{"b"*32:"a"*64}}

    def test_backup_requires_inspected_sha_and_exact_ack(self):
        body={"ack":"BACKUP_ARTIFACT","kind":"website","id":"nem-ngu","tree_sha":"a"*64}
        with patch("agentforge.storage.retention.backup",
                   return_value={"status":"BACKED_UP"}) as backup:
            with self.assertRaises(PermissionError):
                _owner_action(self.server,"/api/retention/backup",body,session={})
            with self.assertRaises(PermissionError):
                _owner_action(self.server,"/api/retention/backup",
                              {**body,"ack":"EXECUTE"},session=self.session)
            with self.assertRaises(PermissionError):
                _owner_action(self.server,"/api/retention/backup",
                              {**body,"delete":True},session=self.session)
            self.assertEqual("BACKED_UP",_owner_action(
                self.server,"/api/retention/backup",body,session=self.session)["status"])
            backup.assert_called_once_with("website","nem-ngu","a"*64,confirm=True)

    def test_quarantine_restore_require_verified_receipt_and_no_extra_fields(self):
        for action,ack in (("quarantine","QUARANTINE_ARTIFACT"),
                           ("restore","RESTORE_ARTIFACT")):
            data={"ack":ack,"backup_id":"b"*32,"tree_sha":"a"*64}
            with self.subTest(action=action),patch(
                    "agentforge.storage.retention."+action,
                    return_value={"status":"OK"}) as fn:
                with self.assertRaises(PermissionError):
                    _owner_action(self.server,"/api/retention/"+action,
                                  data,session={"verified_artifact_backups":{}})
                with self.assertRaises(PermissionError):
                    _owner_action(self.server,"/api/retention/"+action,
                                  {**data,"force":True},session=self.session)
                self.assertEqual("OK",_owner_action(self.server,
                    "/api/retention/"+action,data,session=self.session)["status"])
                fn.assert_called_once_with("b"*32,"a"*64,confirm=True)

if __name__=="__main__":
    unittest.main()
