"""S3 real CSV/SQLite/Task History tests; no external APIs or fabricated revenue."""
import csv
import http.client
import json
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from agentforge import analytics_store as store
from agentforge import analytics_insights as insights
from agentforge import analytics_pipeline as pipeline
from agentforge import dashboard_v0, skill_runner, task_history


def metrics(day="2024-10-02", variant="A", clicks="10", impressions="100"):
    return {
        "date": day, "campaign": "nem-shorts", "channel": "youtube",
        "content": "clip-" + variant.lower(), "variant": variant,
        "impressions": impressions, "views": "50", "clicks": clicks,
        "leads": "3", "orders": "1", "watch_seconds": "400",
    }


def tx(tx_id="receipt-a", kind="revenue", status="owner_confirmed",
       amount="120000", evidence="owner:receipt-1"):
    return {
        "tx_id": tx_id, "date": "2024-10-02", "campaign": "nem-shorts",
        "kind": kind, "status": status, "amount_vnd": amount,
        "evidence_ref": evidence,
    }


class TestS3Analytics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "analytics.sqlite3"
        self.task_db = self.root / "tasks.sqlite3"
        self.inbox = self.root / "workspace" / "analytics" / "inbox"
        self.inbox.mkdir(parents=True)
        self.patches = [
            patch.object(store, "DB", self.db),
            patch.object(store, "INBOX", self.inbox),
            patch.object(task_history, "DEFAULT_DB", self.task_db),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def file(self, name, kind, rows):
        columns = store.PERF_COLUMNS if kind == "performance" else store.LEDGER_COLUMNS
        with (self.inbox / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return name

    def load(self, name="s3-perf.csv", rows=None, *, dataset="production",
             kind="performance", synthetic=False):
        self.file(name, kind, rows if rows is not None else [metrics()])
        return store.import_csv(
            dataset, kind, name, synthetic=synthetic,
            confirm_write=True, db_path=self.db)

    def test_atomic_import_provenance_and_real_measurements(self):
        receipt = self.load()
        self.assertEqual(receipt["status"], "IMPORTED")
        self.assertEqual(receipt["rows"], 1)
        self.assertEqual(len(receipt["source_sha256"]), 64)
        content = insights.content_report("production", db_path=self.db)
        self.assertEqual(content["metrics"]["impressions"], 100)
        self.assertEqual(content["metrics"]["ctr_clicks_per_impression"], .1)
        self.assertEqual(content["metrics"]["average_watch_seconds_per_view"], 8)
        self.assertFalse(content["causal_claim"])
        self.assertEqual(content["sources"]["source_files"][0]["source_kind"], "manual")
        self.assertEqual(content["sources"]["source_files"][0]["sha256"],
                         receipt["source_sha256"])
        self.assertFalse(content["sources"]["external_verification"])

    def test_double_import_is_idempotent(self):
        first = self.load()
        second = store.import_csv(
            "production", "performance", "s3-perf.csv",
            confirm_write=True, db_path=self.db)
        self.assertEqual(second["status"], "ALREADY_IMPORTED")
        self.assertEqual(first["import_id"], second["import_id"])
        self.assertEqual(len(store.load_data("production", db_path=self.db)["performance"]), 1)

    def test_overlapping_keys_rollback_entire_csv(self):
        self.load()
        self.file("s3-second.csv", "performance", [
            metrics(day="2024-10-03"), metrics(day="2024-10-02"),
        ])
        with self.assertRaisesRegex(store.AnalyticsError, "Duplicate observation"):
            store.import_csv("production", "performance", "s3-second.csv",
                             confirm_write=True, db_path=self.db)
        data = store.load_data("production", db_path=self.db)
        self.assertEqual(len(data["performance"]), 1)
        self.assertEqual(len(data["imports"]), 1)

    def test_invalid_rows_dont_create_db(self):
        bads = [
            {"impressions": "-1"}, {"impressions": "1.5"}, {"views": "NaN"},
            {"campaign": "../bad"}, {"channel": "youtube.com"},
            {"date": "2024-02-30"}, {"date": "2035-12-31"},
            {"variant": ""}, {"clicks": "=1+2"},
        ]
        for index, change in enumerate(bads):
            with self.subTest(change=change):
                filename = f"bad-{index}.csv"
                self.file(filename, "performance", [{**metrics(), **change}])
                with self.assertRaises(store.AnalyticsError):
                    store.import_csv("production", "performance", filename,
                                     confirm_write=True, db_path=self.db)
                self.assertFalse(self.db.exists())

    def test_reject_traversal_symlinks_and_extra_csv_fields(self):
        with self.assertRaises(store.AnalyticsError):
            store.import_csv("production", "performance", "../../secret.csv",
                             confirm_write=True, db_path=self.db)
        bad = self.inbox / "bad-extra.csv"
        bad.write_text(",".join(store.PERF_COLUMNS) + ",unexpected\n",
                       encoding="utf-8")
        with self.assertRaises(store.AnalyticsError):
            store.import_csv("production", "performance", "bad-extra.csv",
                             confirm_write=True, db_path=self.db)
        outside = self.root / "outside.csv"
        outside.write_text("outside", encoding="utf-8")
        link = self.inbox / "linked.csv"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(store.AnalyticsError):
            store.import_csv("production", "performance", "linked.csv",
                             confirm_write=True, db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_import_requires_owner_grant_and_confirmation_before_io(self):
        self.file("s3-safe.csv", "performance", [metrics()])
        request = {"dataset": "production", "kind": "performance",
                   "filename": "s3-safe.csv", "source_kind": "manual",
                   "synthetic": False, "confirm_write": False}
        pending = skill_runner.invoke(
            "analytics.import", request,
            grants=("workspace.write",), db_path=self.task_db)
        self.assertEqual(pending["status"], "WAITING_APPROVAL")
        self.assertIn("input.confirm_write", pending["missing"])
        self.assertFalse(self.db.exists())
        request["confirm_write"] = True
        with patch("agentforge.model.generate") as model:
            accepted = skill_runner.invoke(
                "analytics.import", request,
                grants=("workspace.write",), db_path=self.task_db)
            model.assert_not_called()
        self.assertEqual(accepted["status"], "SUCCEEDED")
        self.assertEqual(accepted["result"]["status"], "IMPORTED")
        task = task_history.get_task(accepted["task_id"], db_path=self.task_db)
        self.assertIn("POLICY_GRANTED", [x["name"] for x in task["events"]])

    def test_owner_confirmed_is_not_independently_verified(self):
        self.load()
        self.load("s3-ledger.csv", [
            tx(), tx("paid-a", "cost", "owner_confirmed", "45000", "owner:cost-1"),
            tx("booked", "revenue", "pending", "300000", ""),
            tx("unpaid", "cost", "pending", "22000", ""),
        ], kind="ledger")
        fin = insights.finance_report("production", db_path=self.db)
        self.assertEqual(fin["owner_confirmed_received_vnd"], 120000)
        self.assertEqual(fin["owner_confirmed_paid_vnd"], 45000)
        self.assertEqual(fin["owner_recorded_net_cash_vnd"], 75000)
        self.assertEqual(fin["pending_revenue_vnd"], 300000)
        self.assertEqual(fin["pending_cost_vnd"], 22000)
        self.assertIsNone(fin["verified_net_profit_vnd"])
        self.assertFalse(fin["bank_reconciled"])

    def test_ledger_requires_evidence_reference_for_owner_confirmation(self):
        self.file("bad-ledger.csv", "ledger", [
            tx(evidence="")])
        with self.assertRaisesRegex(store.AnalyticsError, "evidence"):
            store.import_csv("production", "ledger", "bad-ledger.csv",
                             confirm_write=True, db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_duplicate_transaction_id_rejected_with_rollback(self):
        self.load("first-ledger.csv", [tx()], kind="ledger")
        self.file("second-ledger.csv", "ledger",
                  [tx("other"), tx(amount="999999")])
        with self.assertRaisesRegex(store.AnalyticsError, "Duplicate"):
            store.import_csv("production", "ledger", "second-ledger.csv",
                             confirm_write=True, db_path=self.db)
        self.assertEqual(len(store.load_data("production", db_path=self.db)["ledger"]), 1)

    def test_synthetic_cannot_mix_into_real_dataset(self):
        self.load()
        self.file("demo-new.csv", "performance", [metrics(day="2024-10-03")])
        with self.assertRaisesRegex(store.AnalyticsError, "Cannot mix demo"):
            store.import_csv("production", "performance", "demo-new.csv",
                             synthetic=True, confirm_write=True, db_path=self.db)
        self.assertEqual(len(store.load_data("production", db_path=self.db)["imports"]), 1)

    def test_experiment_is_descriptive_not_a_claim_of_winner(self):
        rows = []
        for offset in range(3):
            day = (date(2024, 10, 1) + timedelta(days=offset)).isoformat()
            rows.append(metrics(day=day, variant="A", impressions="100", clicks="5"))
            rows.append(metrics(day=day, variant="B", impressions="100", clicks="10"))
        self.load(rows=rows)
        report = insights.experiment_report("production", "nem-shorts", db_path=self.db)
        self.assertEqual(report["status"], "DESCRIPTIVE_ONLY")
        self.assertEqual(report["ctr_absolute_delta_second_minus_first"], .05)
        self.assertTrue(report["descriptive_sample_sufficient"])
        self.assertIsNone(report["recommended_winner"])
        self.assertFalse(report["causal_claim"])
        self.assertEqual(report["variant_order"], ["A", "B"])
        self.assertEqual(len(report["overlapping_dates"]), 3)
        self.assertEqual(len(report["variants"]["A"]["ctr_wilson_95_approx"]), 2)

    def test_experiment_rejects_mixed_channels_and_missing_variants(self):
        self.load(rows=[metrics(variant="A"), metrics(variant="B")])
        report = insights.experiment_report("production", "nem-shorts", db_path=self.db)
        self.assertFalse(report["descriptive_sample_sufficient"])
        self.assertEqual(report["overlapping_dates"], ["2024-10-02"])
        self.load("other.csv", [metrics(
            day="2024-10-03", variant="A", clicks="7")])
        self.load("channel.csv", [{**metrics(
            day="2024-10-03", variant="B"), "channel": "tiktok"}])
        with self.assertRaisesRegex(store.AnalyticsError, "exactly one channel"):
            insights.experiment_report("production", "nem-shorts", db_path=self.db)

    def test_trend_does_not_claim_market_growth(self):
        self.load(rows=[metrics(day=x) for x in (
            "2024-10-01", "2024-10-03", "2024-10-05")])
        trend = insights.trend_report("production", db_path=self.db)
        self.assertEqual(len(trend["series"]), 3)
        self.assertEqual(trend["interpretation"], "DESCRIPTIVE_ONLY")
        self.assertFalse(trend["external_market_trend_verified"])
        self.assertIn("Observed dates", trend["uncertainty"][-1])

    def test_quality_warns_sparse_data_and_unverified_source(self):
        self.load()
        result = insights.data_quality("production", db_path=self.db)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(any("three observed" in x for x in result["warnings"]))
        self.assertFalse(result["financial_verification"])

    def test_no_zero_division_and_platform_metric_mismatch_warning(self):
        self.load(rows=[metrics(impressions="0", clicks="0")])
        content = insights.content_report("production", db_path=self.db)
        self.assertIsNone(content["metrics"]["ctr_clicks_per_impression"])
        self.assertTrue(any("views exceed impressions" in x
                            for x in content["uncertainty"]))

    def test_demo_is_full_seven_skill_tasks_no_model_or_network(self):
        with patch("agentforge.model.generate") as model:
            with patch("subprocess.run") as proc:
                result = pipeline.synthetic_demo()
                model.assert_not_called()
                proc.assert_not_called()
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertTrue(result["synthetic"])
        self.assertEqual(len(result["imports"]), 2)
        self.assertEqual(len(result["reports"]), 5)
        for receipt in [*result["imports"], *result["reports"].values()]:
            self.assertEqual(receipt["status"], "SUCCEEDED")
        self.assertIsNone(result["reports"]["finance"]["result"]["verified_net_profit_vnd"])
        self.assertTrue(result["reports"]["experiment"]["result"]["synthetic"])
        self.assertEqual(len(task_history.list_tasks(db_path=self.task_db)), 7)
        self.assertEqual(len(store.list_datasets(db_path=self.db)), 1)

    def test_dashboard_analytics_is_local_read_only_and_synthetic_labeled(self):
        demo = pipeline.synthetic_demo()
        overview = dashboard_v0.analytics_overview(analytics_db_path=self.db)
        self.assertEqual(overview[0]["dataset"], demo["dataset"])
        self.assertTrue(overview[0]["synthetic"])
        self.assertIsNone(overview[0]["verified_net_profit_vnd"])
        html = dashboard_v0.render_dashboard(
            db_path=self.task_db, analytics_db_path=self.db)
        self.assertIn("SYNTHETIC DEMO", html)
        self.assertIn("S3 Analytics datasets", html)
        server = dashboard_v0.create_server(
            0, db_path=self.task_db, analytics_db_path=self.db)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/api/analytics")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            api = json.loads(response.read())
            self.assertTrue(api[0]["synthetic"])
            self.assertNotIn("evidence_ref", json.dumps(api))
            conn.close()

            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("POST", "/api/analytics", body="{}")
            response = conn.getresponse()
            self.assertEqual(response.status, 405)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)

    def test_missing_dataset_read_is_not_a_side_effect(self):
        with self.assertRaises(store.AnalyticsError):
            store.load_data("missing", db_path=self.db)
        self.assertFalse(self.db.exists())
        self.assertEqual(store.list_datasets(db_path=self.db), [])

    def test_import_demands_confirmation_even_direct_python_call(self):
        self.file("s3-protected.csv", "performance", [metrics()])
        with self.assertRaises(PermissionError):
            store.import_csv("production", "performance", "s3-protected.csv",
                             db_path=self.db)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
