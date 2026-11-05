"""V3.3 authenticated HTTP retention flow: inspect → backup → verify; no implicit cleanup."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import control_center_v1 as cc
from agentforge.storage import retention

OWNER = "test-retention-owner-code-123"

class RetentionHTTPTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.workspace=self.root/"workspace"
        self.product=self.workspace/"products"/"nem-ngu"
        self.product.mkdir(parents=True)
        (self.product/"index.html").write_text("<html lang='vi'>Nệm ngủ</html>",encoding="utf-8")
        p=patch.object(retention,"WORKSPACE",self.workspace)
        q=patch.object(retention,"BACKUPS",self.root/"data"/"backups"/"agentforge")
        p.start();q.start()
        self.addCleanup(p.stop);self.addCleanup(q.stop)
        self.server=cc.create_server(
            0,owner_code=OWNER,
            task_db_path=self.root/"tasks.sqlite3",
            brain_db_path=self.root/"goals.sqlite3",
            analytics_db_path=self.root/"analytics.sqlite3",
            growth_db_path=self.root/"growth.sqlite3")
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.host="127.0.0.1:"+str(self.server.server_port)
        self.cookie=None
        self.csrf=None

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(4)

    def call(self,method,path,body=None,*,csrf=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=8)
        headers={"Host":self.host}
        if self.cookie: headers["Cookie"]=self.cookie
        if method=="POST":
            headers["Origin"]="http://"+self.host
            headers["Content-Type"]="application/json"
            if csrf and self.csrf: headers["X-CSRF-Token"]=self.csrf
        conn.request(method,path,body=json.dumps(body or {}) if method=="POST" else None,
                     headers=headers)
        resp=conn.getresponse()
        status=resp.status
        cookie=resp.getheader("Set-Cookie")
        raw=resp.read()
        conn.close()
        try: payload=json.loads(raw.decode("utf-8"))
        except (ValueError,UnicodeError): payload={"raw":raw[:100]}
        return status,payload,cookie

    def login(self):
        status,data,cookie=self.call("POST","/api/login",{"code":OWNER})
        self.assertEqual(200,status,data)
        self.cookie=cookie.split(";",1)[0]
        code,session,_=self.call("GET","/api/session")
        self.assertEqual(200,code,session)
        self.csrf=session["csrf"]

    def test_local_retention_requires_login_csrf_and_sha_inspection(self):
        status,_,_=self.call("GET","/api/retention/inventory")
        self.assertEqual(401,status)
        self.login()
        code,inventory,_=self.call("GET","/api/retention/inventory")
        self.assertEqual(200,code,inventory)
        self.assertEqual("nem-ngu",inventory["items"][0]["id"])
        code,_,_=self.call("POST","/api/retention/backup",{
            "ack":"BACKUP_ARTIFACT","kind":"website","id":"nem-ngu","tree_sha":"0"*64})
        self.assertNotEqual(200,code)
        code,review,_=self.call("GET","/api/retention/inspect/website/nem-ngu")
        self.assertEqual(200,code,review)
        action={"ack":"BACKUP_ARTIFACT","kind":"website","id":"nem-ngu",
                "tree_sha":review["tree_sha256"]}
        code,_,_=self.call("POST","/api/retention/backup",action,csrf=False)
        self.assertNotEqual(200,code)
        code,result,_=self.call("POST","/api/retention/backup",action)
        self.assertEqual(200,code,result)
        self.assertTrue(self.product.exists())
        self.assertEqual("BACKED_UP",result["status"])
        bid=result["backup_id"]
        code,verified,_=self.call("GET","/api/retention/verify/"+bid)
        self.assertEqual(200,code,verified)
        self.assertTrue(verified["verified"])
        code,_,_=self.call("POST","/api/retention/quarantine",{
            "ack":"QUARANTINE_ARTIFACT","backup_id":bid,"tree_sha":review["tree_sha256"]})
        self.assertNotEqual(200,code)  # Operations defaults to ACTIVE, must PAUSE explicitly
        self.assertTrue(self.product.exists())

if __name__=="__main__":
    unittest.main()
