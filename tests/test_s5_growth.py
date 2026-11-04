"""S5 end-to-end tests: actual MP4 handoff, owner gates, cash and S3/S4."""
import csv
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from agentforge import analytics_store, brain_store, brain_runner, brain_planner
from agentforge import dashboard_v0, growth_bundle, growth_pipeline, growth_reports
from agentforge import growth_store as store
from agentforge import media_assets, media_render, skill_runner, task_history

HAS_MEDIA = importlib.util.find_spec("PIL") is not None and (
    importlib.util.find_spec("imageio_ffmpeg") is not None)


def story():
    return {"slug": "nem-growth-demo", "title": "Tư vấn nệm mẫu",
            "scenes": [
                {"headline": "Chọn nệm", "caption": "Tìm hiểu nhu cầu trước khi mua.",
                 "duration_seconds": 3},
                {"headline": "Tư vấn", "caption": "Cân nhắc độ nâng đỡ và kích thước.",
                 "duration_seconds": 3},
            ]}


class TestS5Growth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.growth_db = self.root / "growth.sqlite3"
        self.s3_db = self.root / "analytics.sqlite3"
        self.brain_db = self.root / "brain.sqlite3"
        self.task_db = self.root / "tasks.sqlite3"
        self.inbox = self.root / "workspace" / "analytics" / "inbox"
        self.packages = self.root / "workspace" / "growth" / "packages"
        self.media_dir = self.root / "workspace" / "media"
        self.patches = [
            patch.object(store, "DB", self.growth_db),
            patch.object(growth_bundle, "OUT", self.packages),
            patch.object(media_assets, "OUTPUTS", self.media_dir),
            patch.object(media_assets, "INPUTS", self.root / "media_inputs"),
            patch.object(analytics_store, "DB", self.s3_db),
            patch.object(analytics_store, "INBOX", self.inbox),
            patch.object(brain_store, "DB", self.brain_db),
            patch.object(task_history, "DEFAULT_DB", self.task_db),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def create(self, *, campaign="nem-growth", synthetic=False,
               dataset="", budget=30000):
        return store.create_campaign({
            "campaign": campaign, "title": "Tư vấn nệm an toàn",
            "analytics_dataset": dataset, "budget_vnd": budget,
            "synthetic": synthetic,
        }, confirm_write=True)

    def record(self, kind, data):
        return store.record_event(kind, data, confirm_write=True)

    def finance(self, tx_id, kind, status, amount, *, campaign="nem-growth",
                s3_tx_id="", evidence="owner:reference"):
        return self.record("money", {
            "campaign": campaign, "tx_id": tx_id, "kind": kind,
            "status": status, "amount_vnd": amount,
            "evidence_ref": evidence if status == "owner_confirmed" else "",
            "s3_tx_id": s3_tx_id,
        })

    def test_campaign_requires_explicit_owner_write_and_sane_budget(self):
        payload = {"campaign": "nem-growth", "title": "Tư vấn nệm",
                   "analytics_dataset": "", "budget_vnd": 50000,
                   "synthetic": False}
        with self.assertRaises(PermissionError):
            store.create_campaign(payload)
        self.assertFalse(self.growth_db.exists())
        with self.assertRaises(store.GrowthError):
            store.create_campaign({**payload, "budget_vnd": True},
                                  confirm_write=True)
        self.assertFalse(self.growth_db.exists())
        result = store.create_campaign(payload, confirm_write=True)
        self.assertEqual(result["status"], "CREATED")
        self.assertFalse(result["spending_authorized"])
        with self.assertRaisesRegex(store.GrowthError, "already exists"):
            store.create_campaign(payload, confirm_write=True)

    def test_skill_gate_preserves_never_started_task(self):
        payload = {"campaign": "nem-growth", "title": "Tư vấn nệm",
                   "analytics_dataset": "", "budget_vnd": 0,
                   "synthetic": False, "confirm_write": False}
        pending = skill_runner.invoke(
            "growth.campaign_create", payload, grants=("workspace.write",),
            db_path=self.task_db)
        self.assertEqual(pending["status"], "WAITING_APPROVAL")
        self.assertIn("input.confirm_write", pending["missing"])
        self.assertFalse(self.growth_db.exists())
        pending["task_id"]
        new = skill_runner.invoke(
            "growth.campaign_create", {**payload, "confirm_write": True},
            grants=("workspace.write",), db_path=self.task_db)
        self.assertEqual(new["status"], "SUCCEEDED")
        self.assertEqual(new["result"]["status"], "CREATED")
        self.assertEqual(
            task_history.get_task(new["task_id"], db_path=self.task_db)["status"],
            "SUCCEEDED")

    def test_consented_anonymous_lead_state_machine(self):
        self.create()
        with self.assertRaises(store.GrowthError):
            self.record("lead_new", {"campaign": "nem-growth",
                                    "channel": "youtube", "consent_confirmed": False})
        self.assertEqual(store.load_campaign("nem-growth")["leads"], [])
        result = self.record("lead_new", {
            "campaign": "nem-growth", "channel": "youtube", "consent_confirmed": True})
        lid = result["lead_id"]
        self.assertTrue(result["personal_data_stored"] is False)
        for target in ("CONTACTED", "QUALIFIED", "WON"):
            updated = self.record("lead_status", {"lead_id": lid, "status": target})
            self.assertEqual(updated["lead_status"], target)
        with self.assertRaises(store.GrowthError):
            self.record("lead_status", {"lead_id": lid, "status": "LOST"})
        self.assertEqual(growth_reports.report("nem-growth")["lead_counts"]["WON"], 1)
        raw = self.growth_db.read_bytes()
        self.assertNotIn(b"email", raw)
        self.assertNotIn(b"telephone", raw)

    def test_budget_caps_only_recorded_rows_and_no_payment(self):
        self.create(budget=20000)
        a = self.finance("cost-one", "cost", "pending", 15000)
        self.assertFalse(a["payment_executed"])
        with self.assertRaisesRegex(store.GrowthError, "cap exceeded"):
            self.finance("cost-two", "cost", "owner_confirmed", 6000)
        ledger = store.load_campaign("nem-growth")["money"]
        self.assertEqual(len(ledger), 1)
        report = growth_reports.report("nem-growth")
        self.assertEqual(report["bookkeeping_budget_remaining_vnd"], 5000)
        self.assertIsNone(report["verified_net_profit_vnd"])
        self.assertFalse(report["bank_reconciled"])

    def test_pending_commission_not_paid_cash(self):
        self.create()
        self.finance("commission-one", "commission", "pending", 400000)
        self.finance("commission-two", "commission", "owner_confirmed", 200000)
        self.finance("cost-three", "cost", "owner_confirmed", 10000)
        result = growth_reports.report("nem-growth")
        self.assertEqual(result["pending_commission_vnd"], 400000)
        self.assertEqual(result["owner_confirmed_commission_vnd"], 200000)
        self.assertEqual(result["owner_recorded_net_cash_vnd"], 190000)
        self.assertIsNone(result["verified_net_profit_vnd"])
        self.assertFalse(result["marketing_roi_verified"])

    def test_strict_money_schema_rejects_pii_or_external_transfers(self):
        self.create()
        with self.assertRaises(store.GrowthError):
            self.record("money", {
                "campaign": "nem-growth", "tx_id": "transfer-a",
                "kind": "transfer", "status": "owner_confirmed",
                "amount_vnd": 10000, "evidence_ref": "owner:ref", "s3_tx_id": ""})
        with self.assertRaises(store.GrowthError):
            self.record("lead_new", {
                "campaign": "nem-growth", "channel": "youtube",
                "consent_confirmed": True, "phone": "private"})
        self.assertEqual(store.load_campaign("nem-growth")["money"], [])

    def test_reconciliation_crosschecks_owner_ledger_not_bank(self):
        self.inbox.mkdir(parents=True)
        with (self.inbox / "ledger.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=analytics_store.LEDGER_COLUMNS)
            writer.writeheader()
            writer.writerow({
                "tx_id": "payment-record-1", "date": "2026-11-01",
                "campaign": "nem-growth", "kind": "revenue",
                "status": "owner_confirmed", "amount_vnd": "220000",
                "evidence_ref": "owner:receipt-1",
            })
        analytics_store.import_csv("real-source", "ledger", "ledger.csv",
                                   confirm_write=True)
        self.create(dataset="real-source")
        self.finance("commission-one", "commission", "owner_confirmed",
                     220000, s3_tx_id="payment-record-1")
        report = growth_reports.reconcile("nem-growth")
        self.assertEqual(report["status"], "OWNER_BOOKS_MATCH_NOT_BANK_VERIFIED")
        self.assertEqual(report["matched"], 1)
        self.assertIsNone(report["verified_net_profit_vnd"])
        self.assertFalse(report["bank_reconciled"])
        with self.assertRaises(store.GrowthError):
            self.finance("commission-two", "commission", "owner_confirmed",
                         220000, s3_tx_id="payment-record-1")
        self.assertEqual(len(store.load_campaign("nem-growth")["money"]), 1)

    def test_campaign_refuses_crossing_synthetic_and_real_source(self):
        from agentforge import analytics_pipeline
        data = analytics_pipeline.synthetic_demo()
        with self.assertRaisesRegex(store.GrowthError, "provenance"):
            self.create(dataset=data["dataset"], synthetic=False)
        self.assertFalse(self.growth_db.exists())
        created = self.create(dataset=data["dataset"], synthetic=True)
        self.assertTrue(created["synthetic"])

    @unittest.skipUnless(HAS_MEDIA, "Install media extra for real FFmpeg integration")
    def test_real_video_bundle_integrity_and_no_overwrite(self):
        self.create()
        made = media_assets.make_assets(story())
        media_render.render_video(made["run_id"], confirm_external_run=True)
        result = growth_bundle.prepare(
            "nem-growth", "youtube", made["run_id"],
            "Gợi ý chọn nệm", "Tư vấn theo nhu cầu.", confirm_rights=True,
            confirm_write=True)
        path = Path(result["archive_path"])
        self.assertTrue(path.is_file())
        self.assertFalse(result["published"])
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(set(archive.namelist()), {
                "video.mp4", "captions.srt", "post.txt", "manifest.json"})
            manifest = json.loads(archive.read("manifest.json"))
            self.assertFalse(manifest["external_publication_verified"])
            self.assertEqual(manifest["video_sha256"],
                             media_assets.load_manifest(made["run_id"])[1][
                                 "artifacts"]["video.mp4"])
        self.assertEqual(growth_reports.quality_check("nem-growth")["failures"], 0)
        with self.assertRaisesRegex(store.GrowthError, "already exists"):
            growth_bundle.prepare("nem-growth", "youtube", made["run_id"],
                                  "Gợi ý chọn nệm", "Tư vấn theo nhu cầu.",
                                  confirm_rights=True, confirm_write=True)
        self.assertTrue(path.is_file())
        path.write_bytes(b"tampered")
        self.assertEqual(growth_reports.quality_check("nem-growth")["status"], "FAIL")

    @unittest.skipUnless(HAS_MEDIA, "Install media extra")
    def test_manual_post_attestation_requires_correct_public_permalink(self):
        self.create()
        made = media_assets.make_assets(story())
        media_render.render_video(made["run_id"], confirm_external_run=True)
        pack = growth_bundle.prepare("nem-growth", "youtube", made["run_id"],
                                     "Tư vấn nệm", "Hãy tìm hiểu trước khi mua.",
                                     confirm_rights=True, confirm_write=True)
        with self.assertRaises(PermissionError):
            self.record("post_attest", {
                "package_id": pack["package_id"],
                "url": "https://www.youtube.com/shorts/AbCdEf12345",
                "confirm_owner_posted": False})
        for bad in ("http://www.youtube.com/shorts/AbCdEf12345",
                    "https://youtube.com.evil.invalid/shorts/AbCdEf12345",
                    "https://www.tiktok.com/@creator/video/12345678901234567",
                    "https://www.youtube.com/shorts/AbCdEf12345?token=secret"):
            with self.subTest(bad=bad), self.assertRaises(store.GrowthError):
                self.record("post_attest", {"package_id": pack["package_id"],
                                            "url": bad, "confirm_owner_posted": True})
        ok = self.record("post_attest", {
            "package_id": pack["package_id"],
            "url": "https://www.youtube.com/shorts/AbCdEf12345",
            "confirm_owner_posted": True})
        self.assertEqual(ok["status"], "OWNER_REPORTED_POSTED")
        self.assertFalse(ok["external_publication_verified"])
        with self.assertRaises(store.GrowthError):
            self.record("post_attest", {
                "package_id": pack["package_id"],
                "url": "https://www.youtube.com/shorts/AbCdEf12345",
                "confirm_owner_posted": True})
        self.assertEqual(growth_reports.report("nem-growth")["owner_reported_posts"], 1)

    def test_s4_review_template_and_schedulable_read_only(self):
        self.create()
        self.assertTrue(brain_planner.read_only_plan(
            "growth.review", {"campaign": "nem-growth"}))
        goal = brain_planner.propose(
            "Review owner growth", "growth.review", {"campaign": "nem-growth"})
        self.assertEqual(goal["step_count"], 3)
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"])
        completed = brain_runner.execute(goal["goal_id"])
        self.assertEqual(completed["status"], "SUCCEEDED")
        self.assertEqual(completed["executed_steps"], 3)
        items = task_history.list_tasks(db_path=self.task_db)
        self.assertEqual(len(items), 4)
        self.assertEqual(len([t for t in items if t["parent_id"]]), 3)

    def test_dashboard_api_is_read_only_and_synthetic_labeled(self):
        self.create(synthetic=True)
        result = dashboard_v0.growth_overview(growth_db_path=self.growth_db)
        self.assertTrue(result[0]["synthetic"])
        self.assertIsNone(result[0]["verified_net_profit_vnd"])
        html = dashboard_v0.render_dashboard(
            growth_db_path=self.growth_db, db_path=self.task_db,
            analytics_db_path=self.s3_db, brain_db_path=self.brain_db)
        self.assertIn("S5 Revenue &amp; Growth", html.replace(
            "S5 Revenue & Growth", "S5 Revenue &amp; Growth"))
        self.assertIn("SYNTHETIC DEMO", html)
        server = dashboard_v0.create_server(
            0, growth_db_path=self.growth_db, db_path=self.task_db,
            analytics_db_path=self.s3_db, brain_db_path=self.brain_db)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for endpoint in ("/api/growth", "/api/growth/nem-growth"):
                conn = http.client.HTTPConnection("127.0.0.1",
                                                   server.server_port, timeout=3)
                conn.request("GET", endpoint)
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                data = json.loads(response.read())
                self.assertNotIn("evidence_ref", json.dumps(data))
                self.assertNotIn("lead_id", json.dumps(data))
                conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
            conn.request("POST", "/api/growth", body="{}")
            response = conn.getresponse()
            self.assertEqual(response.status, 405)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)

    @unittest.skipUnless(HAS_MEDIA, "Install media extra for complete vertical demo")
    def test_full_real_local_s2_s3_s4_s5_demo_without_cloud(self):
        with patch("agentforge.model.generate") as model:
            with patch("urllib.request.urlopen") as network:
                with self.assertRaises(PermissionError):
                    growth_pipeline.demo()
                result = growth_pipeline.demo(confirm_local_media=True)
                model.assert_not_called()
                network.assert_not_called()
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertTrue(result["synthetic"])
        self.assertTrue(Path(result["video_path"]).is_file())
        self.assertEqual(len(result["packages"]), 2)
        self.assertEqual(result["post_count"], 0)
        self.assertEqual(result["goal_completed_steps"], 3)
        self.assertFalse(result["platform_api_connected"])
        self.assertFalse(result["revenue_verified"])
        self.assertTrue(result["manual_upload_required"])
        self.assertIsNone(result["reports"]["report"]["verified_net_profit_vnd"])
        self.assertTrue(result["reports"]["report"]["synthetic"])
        self.assertEqual(len(store.list_campaigns()), 1)
        self.assertEqual(brain_store.list_goals()[0]["status"], "SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
