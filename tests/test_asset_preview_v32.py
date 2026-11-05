"""V3.2 image preview serves only SHA-checked owner-imported PNG."""
import hashlib
import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import asset_preview, image_studio_v24, web_assets
from agentforge import control_center_v1 as cc

PNG = b"\x89PNG\r\n\x1a\n" + b"safe-synthetic-content"

class AssetPreviewTests(unittest.TestCase):
    def test_sha_verified_source_only(self):
        row = {"status":"ASSET_READY","slug":"demo-site",
               "asset_name":"af-ai-"+("a"*32)+".png",
               "asset_sha":hashlib.sha256(PNG).hexdigest()}
        with patch.object(image_studio_v24,"_row",return_value=row), \
             patch.object(web_assets,"read_image",return_value=(PNG,"image/png")):
            self.assertEqual((PNG,"image/png"),
                             asset_preview.image_for_job("a"*32))
        row["asset_sha"] = "0"*64
        with patch.object(image_studio_v24,"_row",return_value=row), \
             patch.object(web_assets,"read_image",return_value=(PNG,"image/png")):
            with self.assertRaises(PermissionError):
                asset_preview.image_for_job("a"*32)

    def test_unready_image_is_denied(self):
        with patch.object(image_studio_v24,"_row",return_value={
                "status":"SUBMITTING","slug":"demo-site","asset_name":None,"asset_sha":None}):
            with self.assertRaises(PermissionError):
                asset_preview.image_for_job("a"*32)

    def test_image_route_needs_owner_login(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            srv=cc.create_server(port=0,owner_code="owner-check-123456789",
                                 task_db_path=root/"tasks.db",
                                 brain_db_path=root/"goals.db",
                                 analytics_db_path=root/"analytics.db",
                                 growth_db_path=root/"growth.db")
            thread=threading.Thread(target=srv.serve_forever,daemon=True)
            thread.start()
            try:
                conn=http.client.HTTPConnection("127.0.0.1",srv.server_port,timeout=6)
                conn.request("GET","/api/image/"+("a"*32)+"/preview",
                             headers={"Host":f"127.0.0.1:{srv.server_port}"})
                response=conn.getresponse()
                self.assertEqual(401,response.status)
                response.read()
                conn.close()
            finally:
                srv.shutdown();srv.server_close();thread.join(5)

if __name__=="__main__":
    unittest.main()
