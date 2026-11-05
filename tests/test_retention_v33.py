"""V3.3 local artifact backup, verified quarantine, restore and refuse unsafe writes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.storage import retention

class RetentionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.workspace=self.root/"workspace"
        self.backups=self.root/"data"/"backups"/"agentforge"
        self.product=self.workspace/"products"/"nem-ngu"
        self.product.mkdir(parents=True)
        (self.product/"index.html").write_text("<html>Nệm ngủ</html>",encoding="utf-8")
        assets=self.product/"assets"
        assets.mkdir()
        (assets/"hero.png").write_bytes(b"synthetic-image-data")
        self.database=self.root/"data"/"company"/"s4_brain.sqlite3"
        self.database.parent.mkdir(parents=True)
        self.database.write_bytes(b"NEVER_DELETE_SQLITE")
        p=patch.object(retention,"WORKSPACE",self.workspace)
        q=patch.object(retention,"BACKUPS",self.backups)
        p.start();q.start()
        self.addCleanup(p.stop);self.addCleanup(q.stop)

    def test_inventory_and_backup_do_not_mutate_source(self):
        inventory=retention.inventory()
        self.assertEqual(1,inventory["total_items"])
        self.assertEqual("nem-ngu",inventory["items"][0]["id"])
        before=retention.inspect("website","nem-ngu")
        self.assertEqual(2,before["file_count"])
        with self.assertRaises(PermissionError):
            retention.backup("website","nem-ngu",before["tree_sha256"])
        with self.assertRaises(PermissionError):
            retention.backup("website","nem-ngu","0"*64,confirm=True)
        result=retention.backup("website","nem-ngu",before["tree_sha256"],confirm=True)
        self.assertTrue(result["verified"])
        self.assertEqual("BACKED_UP",retention.verify(result["backup_id"])["status"])
        self.assertTrue(self.product.exists())
        self.assertEqual(b"NEVER_DELETE_SQLITE",self.database.read_bytes())
        self.assertEqual(1,len(retention.list_backups()["items"]))

    def test_quarantine_requires_paused_and_can_restore(self):
        before=retention.inspect("website","nem-ngu")
        result=retention.backup("website","nem-ngu",before["tree_sha256"],confirm=True)
        bid=result["backup_id"]
        with patch.object(retention.ops_control,"read",return_value={"mode":"ACTIVE"}):
            with self.assertRaises(PermissionError):
                retention.quarantine(bid,before["tree_sha256"],confirm=True)
        with patch.object(retention.ops_control,"read",return_value={"mode":"PAUSED"}):
            with self.assertRaises(PermissionError):
                retention.quarantine(bid,before["tree_sha256"])
            out=retention.quarantine(bid,before["tree_sha256"],confirm=True)
            self.assertEqual("QUARANTINED",out["status"])
            self.assertFalse(out["permanently_deleted"])
            self.assertFalse(self.product.exists())
            self.assertTrue((self.workspace/".quarantine"/bid/"index.html").exists())
            restored=retention.restore(bid,before["tree_sha256"],confirm=True)
            self.assertTrue(restored["restored"])
            self.assertEqual(before["tree_sha256"],
                             retention.inspect("website","nem-ngu")["tree_sha256"])
        self.assertTrue((self.backups/(bid+".zip")).exists())
        self.assertEqual(b"NEVER_DELETE_SQLITE",self.database.read_bytes())

    def test_changed_source_and_archive_are_rejected(self):
        before=retention.inspect("website","nem-ngu")
        result=retention.backup("website","nem-ngu",before["tree_sha256"],confirm=True)
        bid=result["backup_id"]
        (self.product/"index.html").write_text("changed",encoding="utf-8")
        with patch.object(retention.ops_control,"read",return_value={"mode":"PAUSED"}):
            with self.assertRaises(PermissionError):
                retention.quarantine(bid,before["tree_sha256"],confirm=True)
        self.assertTrue(self.product.exists())
        with (self.backups/(bid+".zip")).open("ab") as stream:
            stream.write(b"corrupt")
        with self.assertRaises(PermissionError):
            retention.verify(bid)

    def test_symlink_and_unknown_kind_fail_closed(self):
        with self.assertRaises(ValueError):
            retention.inspect("database","s4_brain.sqlite3")
        with self.assertRaises(ValueError):
            retention.inspect("website","../data")
        target=self.root/"external"
        target.mkdir()
        (target/"private.txt").write_text("private")
        link=self.product/"external_link"
        try: link.symlink_to(target,target_is_directory=True)
        except (OSError,NotImplementedError): self.skipTest("No Windows symlink privilege")
        with self.assertRaises(PermissionError):
            retention.inspect("website","nem-ngu")
        self.assertTrue((target/"private.txt").exists())

    def test_restore_refuses_to_overwrite_existing_destination(self):
        before=retention.inspect("website","nem-ngu")
        item=retention.backup("website","nem-ngu",before["tree_sha256"],confirm=True)
        bid=item["backup_id"]
        with patch.object(retention.ops_control,"read",return_value={"mode":"PAUSED"}):
            retention.quarantine(bid,before["tree_sha256"],confirm=True)
            self.product.mkdir(parents=True)
            (self.product/"index.html").write_text("newer customer content",encoding="utf-8")
            with self.assertRaises(FileExistsError):
                retention.restore(bid,before["tree_sha256"],confirm=True)
            self.assertEqual("newer customer content",(self.product/"index.html").read_text())
            self.assertEqual("QUARANTINED",retention.verify(bid)["status"])
            self.assertTrue((self.workspace/".quarantine"/bid).is_dir())

    def test_quarantine_never_deletes_archive_or_sqlite(self):
        original=retention.inspect("website","nem-ngu")
        item=retention.backup("website","nem-ngu",original["tree_sha256"],confirm=True)
        with patch.object(retention.ops_control,"read",return_value={"mode":"PAUSED"}):
            receipt=retention.quarantine(item["backup_id"],original["tree_sha256"],confirm=True)
        self.assertFalse(receipt["permanently_deleted"])
        self.assertTrue((self.backups/(item["backup_id"]+".zip")).is_file())
        self.assertEqual(b"NEVER_DELETE_SQLITE",self.database.read_bytes())

    def test_file_size_limit_enforced(self):
        with patch.object(retention,"MAX_FILE_BYTES",10):
            with self.assertRaises(ValueError):
                retention.inspect("website","nem-ngu")

if __name__=="__main__":
    unittest.main()
