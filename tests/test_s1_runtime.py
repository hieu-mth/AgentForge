"""S1 contract, permission, persistence, and adapter regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import skill_runner, task_history


class TestS1SkillRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tasks.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_deny_model_without_grants_before_call_and_persist(self):
        with patch("agentforge.product_builder.propose") as model:
            response = skill_runner.invoke(
                "web.create", {"slug": "nem-tu-van", "brief": "Trang giới thiệu nệm"},
                db_path=self.db,
            )
            model.assert_not_called()
        self.assertEqual(response["status"], "WAITING_APPROVAL")
        self.assertIn("model.invoke", response["missing"])
        self.assertIn("confirm_model_call", response["missing"])
        task = task_history.get_task(response["task_id"], db_path=self.db)
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        self.assertEqual([e["name"] for e in task["events"]],
                         ["CREATED", "WAITING_APPROVAL"])

    def test_resume_only_unexecuted_after_explicit_grants(self):
        data = {"slug": "nem-tu-van", "brief": "Trang giới thiệu nệm"}
        pending = skill_runner.invoke("web.create", data, db_path=self.db)
        still = skill_runner.resume_waiting(pending["task_id"], db_path=self.db)
        self.assertEqual(still["status"], "WAITING_APPROVAL")
        with patch("agentforge.product_builder.propose", return_value={
            "proposal_id": "a" * 32, "project_slug": "nem-tu-van",
            "sha256": "b" * 64, "execution_authorized": False,
        }) as handler:
            approved = skill_runner.resume_waiting(
                pending["task_id"], grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True, db_path=self.db)
            handler.assert_called_once_with("nem-tu-van", "Trang giới thiệu nệm")
        self.assertEqual(approved["status"], "SUCCEEDED")
        self.assertTrue(approved["executed"])
        self.assertEqual(task_history.get_task(pending["task_id"], db_path=self.db)["status"],
                         "SUCCEEDED")
        with self.assertRaises(ValueError):
            skill_runner.resume_waiting(pending["task_id"], db_path=self.db)

    def test_read_only_quality_single_adapter(self):
        report = {"status": "PASS", "failures": 0, "warnings": 0,
                  "findings": [], "sha256": "a" * 64}
        with patch("agentforge.product_quality.check_project", return_value=report) as call:
            response = skill_runner.invoke(
                "web.quality_check", {"slug": "nem-tu-van"}, db_path=self.db)
            call.assert_called_once_with("nem-tu-van")
        self.assertEqual(response["status"], "SUCCEEDED")
        self.assertEqual(response["result"]["status"], "PASS")

    def test_browser_needs_two_approvals_and_strict_grant(self):
        payload = {"slug": "nem-tu-van", "confirm_browser_run": True,
                   "browser_channel": "msedge"}
        with patch("agentforge.browser_validation.validate") as validate:
            pending = skill_runner.invoke("web.browser_test", payload, db_path=self.db)
            validate.assert_not_called()
        self.assertIn("browser.run", pending["missing"])
        with patch("agentforge.browser_validation.validate", return_value={
            "run_id": "c" * 32, "status": "PASS",
        }) as validate:
            result = skill_runner.resume_waiting(
                pending["task_id"], grants=("browser.run",),
                confirm_browser_run=True, db_path=self.db)
            validate.assert_called_once_with(
                "project", "nem-tu-van", confirm_browser_run=True,
                browser_channel="msedge")
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_browser_payload_must_confirm_even_when_cli_confirmed(self):
        response = skill_runner.invoke(
            "web.browser_test", {"slug": "nem-tu-van", "confirm_browser_run": False},
            grants=("browser.run",), confirm_browser_run=True, db_path=self.db)
        self.assertIn("input.confirm_browser_run", response["missing"])

    def test_research_requires_model_network_and_write(self):
        with patch("agentforge.research.run", return_value={
            "research_id": "d" * 32, "status": "LEADS_ONLY_NOT_VERIFIED",
        }) as run:
            pending = skill_runner.invoke(
                "research.opportunity", {"topic": "Nghiên cứu cơ hội nệm"},
                confirm_model_call=True, grants=("model.invoke",),
                db_path=self.db)
            run.assert_not_called()
            result = skill_runner.resume_waiting(
                pending["task_id"], confirm_model_call=True,
                grants=("model.invoke", "workspace.write", "network.search"),
                db_path=self.db)
            run.assert_called_once_with("Nghiên cứu cơ hội nệm")
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_source_review_uses_old_owner_approval_and_host_allowlist(self):
        payload = {"task_id": "test-task", "allowed_hosts": ["example.org"],
                   "approve_read_only": True}
        with patch("agentforge.source_review.run_review", return_value={
            "task_id": "test-task", "review_status": "QUOTE_REVIEW_ONLY",
            "matched_quotes": 1,
        }) as run:
            result = skill_runner.invoke(
                "research.source_review", payload,
                grants=("workspace.write", "network.read", "model.invoke"),
                confirm_model_call=True, db_path=self.db)
            run.assert_called_once_with(
                "test-task", ["example.org"], max_pages=4, approve_read_only=True)
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_invalid_contract_or_input_fails_closed_without_task(self):
        with self.assertRaises(ValueError):
            skill_runner.invoke("web.create", {"slug": "nem-tu-van"}, db_path=self.db)
        self.assertFalse(self.db.exists())
        with self.assertRaises(PermissionError):
            skill_runner.invoke("unknown.skill", {"slug": "nem-tu-van"}, db_path=self.db)
        with self.assertRaises(PermissionError):
            skill_runner.invoke(
                "web.quality_check", {"slug": "nem-tu-van"},
                grants=("admin.root",), db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_tampered_manifest_cannot_remove_code_level_grants(self):
        from agentforge import skill_registry
        original = skill_registry.load_skill("web.create")
        forged = {**original, "required_permissions": ["workspace.read"]}
        with patch.object(skill_registry, "load_skill", return_value=forged):
            with self.assertRaises(PermissionError):
                skill_runner.invoke("web.create", {"slug": "nem-tu-van", "brief": "Test"},
                                    db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_web_builder_validation_errors_are_safe_and_actionable(self):
        cases = [
            ("Disallowed active/remote content in index.html: remote URL at line 5; key=SECRET",
             "HTML_REMOTE_URL"),
            ("Disallowed active/remote content in index.html: active/embedded content at line 6; SECRET",
             "HTML_ACTIVE_CONTENT"),
            ("Disallowed active/remote content in index.html: NUL byte SECRET",
             "HTML_UNSAFE_CONTENT"),
            ("Only a local app.js script source is allowed", "HTML_SCRIPT_SOURCE"),
            ("Model returned an unexpected object", "BUILDER_SCHEMA_INVALID"),
            ("Builder reply must start with a complete HTML document", "HTML_INCOMPLETE"),
            ("Structured website content invalid: SECRET", "WEB_COPY_INVALID"),
            ("Invalid owner phone number", "OWNER_CONTACT_INVALID"),
            ("A novel error containing api_key=SECRET", "BUILDER_INVALID_OUTPUT"),
        ]
        for detail, expected in cases:
            with self.subTest(detail=expected):
                message = skill_runner._safe_failure("web.create", ValueError(detail))
                self.assertTrue(message.startswith(expected + ":"))
                self.assertNotIn("SECRET", message)

    def test_execution_failure_is_audited_without_leaking_exception_body(self):
        with patch("agentforge.product_quality.check_project",
                   side_effect=RuntimeError("api_key=secret private-body")):
            result = skill_runner.invoke(
                "web.quality_check", {"slug": "nem-tu-van"}, db_path=self.db)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(task_history.get_task(result["task_id"], db_path=self.db)["status"],
                         "FAILED")
        self.assertNotIn("secret", self.db.read_bytes().decode("utf-8", errors="ignore"))

    def test_recover_marks_orphaned_running_without_replay(self):
        task_id = task_history.create_task("skill", "web.create", {"slug": "test"},
                                           db_path=self.db)
        task_history.transition(task_id, "RUNNING", db_path=self.db)
        self.assertEqual(task_history.recover(db_path=self.db), 1)
        self.assertEqual(task_history.recover(db_path=self.db), 0)
        self.assertEqual(task_history.get_task(task_id, db_path=self.db)["status"],
                         "INTERRUPTED")
        with self.assertRaises(ValueError):
            skill_runner.resume_waiting(task_id, db_path=self.db)

    def test_task_state_machine_and_event_order(self):
        tid = task_history.create_task("skill", "web.quality_check",
                                       {"slug": "nem-tu-van"}, db_path=self.db)
        task_history.transition(tid, "RUNNING", db_path=self.db)
        task_history.checkpoint(tid, "STATIC_DONE", {"passed": True}, db_path=self.db)
        task_history.transition(tid, "SUCCEEDED", db_path=self.db)
        with self.assertRaises(ValueError):
            task_history.transition(tid, "RUNNING", db_path=self.db)
        task = task_history.get_task(tid, db_path=self.db)
        self.assertEqual([e["name"] for e in task["events"]],
                         ["CREATED", "RUNNING", "STATIC_DONE", "SUCCEEDED"])
        self.assertEqual(len(task_history.list_tasks(db_path=self.db)), 1)

    def test_database_path_symlink_rejected(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        link = Path(self.tmp.name) / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(PermissionError):
            task_history.create_task("skill", "web.create", {}, db_path=link / "db.sqlite")
        self.assertFalse((outside / "db.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
