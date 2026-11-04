"""C8F checkpoint workflow: no automatic browser, model retry or apply."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder as builder
from agentforge import product_cycle as cycle
from agentforge import product_revision as revision
from agentforge import browser_validation as browser

HTML = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Shop</title><style>@media(max-width:600px){body{margin:0}}'
        '</style></head><body><h1>Old</h1></body></html>')
NEW = HTML.replace("<h1>Old", "<h1>New")
PASS_ID = "c"*32
FAIL_ID = "d"*32
CAND_ID = "e"*32


class TestProductCycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(builder, "ROOT", self.root)
        self.products_patch = patch.object(
            builder, "PRODUCTS", self.root / "workspace" / "products")
        self.root_patch.start()
        self.products_patch.start()
        self.source = builder.PRODUCTS / "shop-landing" / "index.html"
        self.source.parent.mkdir(parents=True)
        self.source.write_text(HTML, encoding="utf-8")
        self.browser_runs = []
        self.model_prompts = []

    def tearDown(self):
        self.products_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def make_report(self, kind="project", *, run_id=PASS_ID,
                    status="PASS", findings=None, revision_id=None):
        if findings is None:
            findings = []
        if kind == "project":
            identifier = "shop-landing"
            sha = revision._hash(self.source.read_bytes())
        else:
            identifier = revision_id
            doc, _, _ = revision._read_revision(revision_id)
            sha = revision._hash(doc["files"][0]["content"].encode("utf-8"))
        nfail = sum(x["severity"] == "FAIL" for x in findings)
        nwarn = sum(x["severity"] == "WARN" for x in findings)
        if status == "WARN" and not nwarn:
            nwarn = 1
        data = {
            "schema_version": 1, "run_id": run_id,
            "created_at": "2026-11-04T11:00:00+00:00",
            "target": kind, "identifier": identifier,
            "project_slug": "shop-landing",
            "source_sha256": sha, "browser_channel": "msedge",
            "status": status, "failures": nfail, "warnings": nwarn,
            "findings": findings, "static_status": "PASS",
            "viewports": [],
            "browser_rendered": True, "javascript_executed": True,
            "browser_run_approved": True, "product_modified": False,
            "security_verified": False, "spending_authorized": False,
            "deployment_authorized": False,
        }
        for name, width, height in browser.VIEWPORTS:
            data["viewports"].append({
                "viewport": name, "width": width, "height": height,
                "document_width": width + (20 if status == "FAIL" and name == "mobile" else 0),
                "document_height": 1200,
                "javascript_error_count": 0, "blocked_request_count": 0,
                "screenshot_path": None,
            })
        path = (self.root / "data" / "company" / "product_builder"
                / "browser_checks" / kind / identifier / run_id / "report.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    @staticmethod
    def failure():
        return [{"rule": "horizontal_overflow", "severity": "FAIL",
                 "viewport": "mobile", "message": "page too wide"}]

    def failing_baseline(self):
        self.make_report(run_id=FAIL_ID, status="FAIL", findings=self.failure())
        return cycle.start("shop-landing", report_run_id=FAIL_ID)["cycle_id"]

    def fake_model(self, prompt, *, worker_id):
        self.model_prompts.append(prompt)
        self.assertEqual(worker_id, "product_builder")
        return NEW

    def runner(self, kind, identifier, *, confirm_browser_run, browser_channel):
        self.assertTrue(confirm_browser_run)
        self.browser_runs.append((kind, browser_channel))
        rid = PASS_ID if kind == "project" else CAND_ID
        self.make_report(kind, run_id=rid, revision_id=identifier if kind == "revision" else None)
        return {"status": "PASS", "run_id": rid}

    def test_start_from_pass_report_without_side_effects(self):
        self.make_report()
        with (patch("agentforge.model.generate") as model,
              patch("agentforge.browser_validation._playwright") as launch):
            result = cycle.start("shop-landing", report_run_id=PASS_ID)
            model.assert_not_called()
            launch.assert_not_called()
        self.assertEqual(result["status"], "NO_FIX_NEEDED")
        self.assertEqual(result["baseline_status"], "PASS")
        self.assertFalse(result["automatic_apply"])

    def test_pass_propose_never_calls_model_even_when_approved(self):
        self.make_report()
        sid = cycle.start("shop-landing", report_run_id=PASS_ID)["cycle_id"]
        with patch("agentforge.model.generate") as model:
            self.assertEqual(cycle.propose(sid, confirm_model_call=True)["status"],
                             "NO_FIX_NEEDED")
            model.assert_not_called()
        self.assertIsNone(cycle._read_event(sid, "model_attempt"))

    def test_fresh_start_awaits_browser_without_running_it(self):
        result = cycle.start("shop-landing")
        self.assertEqual(result["status"], "AWAITING_BROWSER_TEST")
        self.assertIsNone(cycle._read_event(result["cycle_id"], "baseline_attempt"))

    def test_baseline_requires_explicit_browser_permission(self):
        sid = cycle.start("shop-landing")["cycle_id"]
        with self.assertRaises(PermissionError):
            cycle.test(sid, browser_runner=self.runner)
        self.assertIsNone(cycle._read_event(sid, "baseline_attempt"))

    def test_one_baseline_browser_run_and_checkpoint(self):
        sid = cycle.start("shop-landing")["cycle_id"]
        result = cycle.test(sid, confirm_browser_run=True, browser_channel="msedge",
                            browser_runner=self.runner)
        self.assertEqual(result["status"], "NO_FIX_NEEDED")
        self.assertEqual(self.browser_runs, [("project", "msedge")])
        self.assertIsNotNone(cycle._read_event(sid, "baseline_result"))
        self.assertEqual(self.source.read_text(encoding="utf-8"), HTML)
        with self.assertRaisesRegex(RuntimeError, "already attempted"):
            cycle.test(sid, confirm_browser_run=True, browser_runner=self.runner)
        self.assertEqual(len(self.browser_runs), 1)

    def test_attached_report_cannot_be_retested(self):
        self.make_report()
        sid = cycle.start("shop-landing", report_run_id=PASS_ID)["cycle_id"]
        with self.assertRaisesRegex(RuntimeError, "already has an attached"):
            cycle.test(sid, confirm_browser_run=True, browser_runner=self.runner)
        self.assertEqual(self.browser_runs, [])

    def test_browser_exception_still_consumes_one_attempt(self):
        sid = cycle.start("shop-landing")["cycle_id"]
        def fail(*a, **kw):
            raise RuntimeError("browser unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            cycle.test(sid, confirm_browser_run=True, browser_runner=fail)
        self.assertEqual(cycle.inspect(sid)["status"],
                         "BASELINE_ATTEMPT_INTERRUPTED")
        with self.assertRaisesRegex(RuntimeError, "already attempted"):
            cycle.test(sid, confirm_browser_run=True, browser_runner=fail)

    def test_source_changed_after_cycle_start_refused(self):
        sid = cycle.start("shop-landing")["cycle_id"]
        self.source.write_text(HTML.replace("Old", "Other"), encoding="utf-8")
        self.assertEqual(cycle.inspect(sid)["status"], "STALE_CYCLE")
        with self.assertRaisesRegex(RuntimeError, "STALE_CYCLE"):
            cycle.test(sid, confirm_browser_run=True, browser_runner=self.runner)

    def test_stale_reused_report_rejected(self):
        self.make_report()
        self.source.write_text(HTML.replace("Old", "Other"), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "STALE_BROWSER_REPORT"):
            cycle.start("shop-landing", report_run_id=PASS_ID)

    def test_wrong_project_report_rejected(self):
        self.make_report()
        other = builder.PRODUCTS / "other-shop" / "index.html"
        other.parent.mkdir(parents=True)
        other.write_text(HTML, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "different project"):
            cycle.start("other-shop", report_run_id=PASS_ID)

    def test_malformed_report_change_refused_after_checkpoint(self):
        self.make_report()
        sid = cycle.start("shop-landing", report_run_id=PASS_ID)["cycle_id"]
        path = (self.root / "data" / "company" / "product_builder"
                / "browser_checks" / "project" / "shop-landing" / PASS_ID / "report.json")
        doc = json.loads(path.read_text())
        doc["viewports"][0]["document_height"] = 1201
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "CHANGED_REPORT"):
            cycle.inspect(sid)

    def test_failed_baseline_requires_owner_model_consent(self):
        sid = self.failing_baseline()
        self.assertEqual(cycle.inspect(sid)["status"], "FIX_PROPOSAL_AVAILABLE")
        with self.assertRaises(PermissionError):
            cycle.propose(sid, model_client=self.fake_model)
        self.assertEqual(len(self.model_prompts), 0)
        self.assertIsNone(cycle._read_event(sid, "model_attempt"))

    def test_failed_baseline_builds_single_c8b_revision(self):
        sid = self.failing_baseline()
        state = cycle.propose(sid, confirm_model_call=True,
                              model_client=self.fake_model)
        self.assertEqual(state["status"], "AWAITING_CANDIDATE_BROWSER_TEST")
        self.assertEqual(len(self.model_prompts), 1)
        self.assertIn("Fix horizontal overflow", self.model_prompts[0])
        self.assertEqual(self.source.read_text(encoding="utf-8"), HTML)
        self.assertIsNone(cycle._read_event(sid, "candidate_attempt"))
        with self.assertRaisesRegex(RuntimeError, "no retry"):
            cycle.propose(sid, confirm_model_call=True,
                          model_client=self.fake_model)
        self.assertEqual(len(self.model_prompts), 1)

    def test_failed_model_consumes_attempt_without_retry(self):
        sid = self.failing_baseline()
        def fail(*args, **kwargs):
            raise RuntimeError("gateway timeout")
        with self.assertRaisesRegex(RuntimeError, "gateway timeout"):
            cycle.propose(sid, confirm_model_call=True, model_client=fail)
        self.assertEqual(cycle.inspect(sid)["status"], "MODEL_ATTEMPT_INTERRUPTED")
        with self.assertRaisesRegex(RuntimeError, "no retry"):
            cycle.propose(sid, confirm_model_call=True, model_client=fail)
        self.assertEqual(self.source.read_text(encoding="utf-8"), HTML)

    def test_candidate_requires_explicit_browser_confirmation(self):
        sid = self.failing_baseline()
        cycle.propose(sid, confirm_model_call=True, model_client=self.fake_model)
        with self.assertRaises(PermissionError):
            cycle.test_revision(sid, browser_runner=self.runner)
        self.assertEqual(self.browser_runs, [])

    def test_candidate_pass_leaves_owner_approval_gate_intact(self):
        sid = self.failing_baseline()
        proposed = cycle.propose(sid, confirm_model_call=True,
                                 model_client=self.fake_model)
        candidate = cycle.test_revision(sid, confirm_browser_run=True,
                                        browser_channel="chrome",
                                        browser_runner=self.runner)
        self.assertEqual(candidate["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(candidate["candidate_run_id"], CAND_ID)
        self.assertEqual(self.browser_runs, [("revision", "chrome")])
        self.assertEqual(self.source.read_text(encoding="utf-8"), HTML)
        with self.assertRaises(PermissionError):
            revision.apply(proposed["revision_id"], sha256=
                           revision.inspect(proposed["revision_id"])["sha256"])

    def test_candidate_browser_is_one_attempt_only(self):
        sid = self.failing_baseline()
        cycle.propose(sid, confirm_model_call=True, model_client=self.fake_model)
        cycle.test_revision(sid, confirm_browser_run=True,
                            browser_runner=self.runner)
        with self.assertRaisesRegex(RuntimeError, "already attempted"):
            cycle.test_revision(sid, confirm_browser_run=True,
                                browser_runner=self.runner)
        self.assertEqual(len(self.browser_runs), 1)

    def test_candidate_fail_requires_owner_review_not_apply(self):
        sid = self.failing_baseline()
        result = cycle.propose(sid, confirm_model_call=True,
                               model_client=self.fake_model)
        def fail_candidate(kind, identifier, **kw):
            self.make_report("revision", run_id=CAND_ID,
                             status="FAIL", findings=self.failure(),
                             revision_id=identifier)
            return {"run_id": CAND_ID, "status": "FAIL"}
        state = cycle.test_revision(sid, confirm_browser_run=True,
                                    browser_runner=fail_candidate)
        self.assertEqual(state["status"], "CANDIDATE_FAILED")
        self.assertEqual(self.source.read_text(encoding="utf-8"), HTML)
        self.assertFalse(cycle._read_event(sid, "model_result").get("applied", False))

    def test_candidate_report_tamper_detected(self):
        sid = self.failing_baseline()
        cycle.propose(sid, confirm_model_call=True, model_client=self.fake_model)
        cycle.test_revision(sid, confirm_browser_run=True,
                            browser_runner=self.runner)
        rid = cycle._read_event(sid, "model_result")["revision_id"]
        path = (self.root / "data" / "company" / "product_builder"
                / "browser_checks" / "revision" / rid / CAND_ID / "report.json")
        record = json.loads(path.read_text())
        record["viewports"][0]["document_height"] = 1400
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "CHANGED_REPORT"):
            cycle.inspect(sid)

    def test_manually_applied_revision_is_detected_not_auto_applied(self):
        sid = self.failing_baseline()
        proposed = cycle.propose(sid, confirm_model_call=True,
                                 model_client=self.fake_model)
        cycle.test_revision(sid, confirm_browser_run=True,
                            browser_runner=self.runner)
        rid = proposed["revision_id"]
        receipt = revision.apply(
            rid, confirm_write=True,
            sha256=revision.inspect(rid)["sha256"])
        self.assertTrue(Path(receipt["backup_path"]).exists())
        state = cycle.inspect(sid)
        self.assertEqual(state["status"], "APPLIED_VIA_C8B")
        self.assertFalse(state["automatic_apply"])

    def test_unknown_failure_never_calls_ai(self):
        unknown = [{"rule": "future_rule", "severity": "FAIL",
                    "viewport": "mobile", "message": "unknown"}]
        self.make_report(run_id=FAIL_ID, status="FAIL", findings=unknown)
        sid = cycle.start("shop-landing", report_run_id=FAIL_ID)["cycle_id"]
        with patch("agentforge.model.generate") as model:
            self.assertEqual(cycle.propose(sid, confirm_model_call=True)["status"],
                             "MANUAL_REVIEW_REQUIRED")
            model.assert_not_called()

    def test_unsafe_cycle_id_rejected(self):
        with self.assertRaises(ValueError):
            cycle.inspect("../bad")

    def test_missing_cycle_refused(self):
        with self.assertRaises(FileNotFoundError):
            cycle.inspect("b"*32)

    def test_invalid_browser_channel_refused_without_checkpoint(self):
        sid = cycle.start("shop-landing")["cycle_id"]
        with self.assertRaisesRegex(ValueError, "Invalid installed"):
            cycle.test(sid, confirm_browser_run=True,
                       browser_channel="firefox", browser_runner=self.runner)
        self.assertIsNone(cycle._read_event(sid, "baseline_attempt"))

    def test_baseline_report_missing_refused_before_model(self):
        sid = self.failing_baseline()
        path = (self.root / "data" / "company" / "product_builder"
                / "browser_checks" / "project" / "shop-landing" / FAIL_ID / "report.json")
        path.unlink()
        with patch("agentforge.model.generate") as model:
            with self.assertRaises(FileNotFoundError):
                cycle.propose(sid, confirm_model_call=True)
            model.assert_not_called()

    def test_empty_cycle_checkpoint_not_silently_accepted(self):
        sid = cycle.start("shop-landing")["cycle_id"]
        cycle._path(sid, "start").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            cycle.inspect(sid)

    def test_no_external_execution_on_plain_inspection(self):
        self.make_report()
        sid = cycle.start("shop-landing", report_run_id=PASS_ID)["cycle_id"]
        with (patch("agentforge.model.generate") as model,
              patch("subprocess.run") as shell,
              patch("agentforge.browser_validation._playwright") as launch):
            cycle.inspect(sid)
            model.assert_not_called()
            shell.assert_not_called()
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
