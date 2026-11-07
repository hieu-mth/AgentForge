"""V4.1 source-aware app revisions: immutable versions, visible diff, no replay."""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import (
    brain_planner, brain_runner, brain_store, task_history, webapp_builder,
    webapp_feedback,
)
from tests.test_webapp_builder_v40 import SPEC, BRIEF


def revision_spec():
    revised = deepcopy(SPEC)
    revised["headline"] = "Chọn đồ mỗi ngày theo cách mới"
    revised["accent"] = "#163f75"
    revised["products"][0]["name"] = "Tai nghe Aurora phiên bản demo"
    return revised


class WebappRevisionV41Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.brain = root / "brain.sqlite3"
        self.tasks = root / "tasks.sqlite3"
        for key, val in [
            ("PROJECTS", root / "workspace" / "webapps"),
            ("PROPOSALS", root / "proposals"),
        ]:
            p = patch.object(webapp_builder, key, val)
            p.start()
            self.addCleanup(p.stop)

    def original(self):
        with patch("agentforge.model.generate_json", return_value=SPEC) as model:
            first = webapp_builder.propose("demo-original", BRIEF)
            model.assert_called_once()
        return first

    def revise(self, original, *, response=None, feedback=None):
        if response is None:
            response = revision_spec()
        if feedback is None:
            feedback = "Đổi màu xanh navy, đổi tiêu đề và tên sản phẩm đầu."
        with patch("agentforge.model.generate_json", return_value=response) as model:
            next_version = webapp_builder.propose(
                "demo-revised", BRIEF,
                source_proposal_id=original["proposal_id"],
                source_sha256=original["sha256"],
                revision_feedback=feedback)
            model.assert_called_once()
            self.assertIn(original["proposal_id"], model.call_args.args[0])
            self.assertIn(feedback, model.call_args.args[0])
            self.assertIn(SPEC["headline"], model.call_args.args[0])
        return next_version

    def test_revision_only_changes_intended_catalogue_and_preserves_source(self):
        original = self.original()
        original_document = Path(original["proposal_path"]).read_bytes()
        updated = self.revise(original)
        self.assertTrue(updated["revision"])
        self.assertIn("accent", updated["changed_fields"])
        self.assertIn("headline", updated["changed_fields"])
        self.assertFalse(webapp_builder.PROJECTS.exists())
        self.assertEqual(Path(original["proposal_path"]).read_bytes(), original_document)
        diff = webapp_builder.compare(updated["proposal_id"])
        self.assertTrue(diff["revision"])
        self.assertTrue(diff["visible_change"])
        self.assertEqual(diff["source_proposal_id"], original["proposal_id"])
        self.assertIn("src/catalog.js", diff["changed_files"])
        self.assertIn("app.json", diff["changed_files"])
        source, _ = webapp_builder._read_proposal(original["proposal_id"])
        revised, _ = webapp_builder._read_proposal(updated["proposal_id"])
        source_files = {x["path"]: x["content"] for x in source["files"]}
        revised_files = {x["path"]: x["content"] for x in revised["files"]}
        for protected in ("src/App.jsx", "src/store.js", "src/main.jsx", "vite.config.js",
                          "src/styles.css", "tests/store.test.js"):
            self.assertEqual(source_files[protected], revised_files[protected])
        self.assertNotEqual(source_files["src/catalog.js"], revised_files["src/catalog.js"])

    def test_unchanged_and_metadata_only_model_output_rejected(self):
        original = self.original()
        with patch("agentforge.model.generate_json", return_value=deepcopy(SPEC)) as model:
            with self.assertRaisesRegex(ValueError, "APP_REVISION_UNCHANGED"):
                webapp_builder.propose(
                    "demo-revised", BRIEF,
                    source_proposal_id=original["proposal_id"],
                    source_sha256=original["sha256"],
                    revision_feedback="Thay đổi bảng màu nhưng AI trả lại trang cũ")
            model.assert_called_once()
        self.assertEqual(len(list(webapp_builder.PROPOSALS.glob("*.json"))), 1)

    def test_stale_sha_is_rejected_before_model_call(self):
        original = self.original()
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaisesRegex(PermissionError, "APP_SOURCE_STALE"):
                webapp_builder.propose(
                    "demo-revised", BRIEF,
                    source_proposal_id=original["proposal_id"],
                    source_sha256="0" * 64,
                    revision_feedback="Thay đổi tên thương hiệu và tiêu đề")
            model.assert_not_called()

    def test_revision_provenance_is_covered_by_signed_sha(self):
        original = self.original()
        updated = self.revise(original)
        path = Path(updated["proposal_path"])
        original_document = json.loads(path.read_text(encoding="utf-8"))
        for change in ("feedback", "source_sha256", "source_proposal_id"):
            document = deepcopy(original_document)
            document["revision"][change] = "0" * (64 if change == "source_sha256"
                                                    else 32 if change == "source_proposal_id"
                                                    else 20)
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with self.subTest(change=change), self.assertRaises(ValueError):
                webapp_builder._read_proposal(updated["proposal_id"])
        self.assertFalse(webapp_builder.PROJECTS.exists())

    def test_owner_apply_writes_new_version_without_overwriting_original(self):
        original = self.original()
        updated = self.revise(original)
        source_applied = webapp_builder.apply(
            original["proposal_id"], sha256=original["sha256"], confirm_write=True)
        new_applied = webapp_builder.apply(
            updated["proposal_id"], sha256=updated["sha256"], confirm_write=True)
        self.assertEqual(source_applied["status"], "FILES_WRITTEN_NOT_EXECUTED")
        self.assertEqual(new_applied["status"], "FILES_WRITTEN_NOT_EXECUTED")
        original_app = webapp_builder.PROJECTS / "demo-original" / "src" / "catalog.js"
        changed_app = webapp_builder.PROJECTS / "demo-revised" / "src" / "catalog.js"
        self.assertTrue(original_app.is_file())
        self.assertTrue(changed_app.is_file())
        self.assertNotEqual(original_app.read_bytes(), changed_app.read_bytes())
        self.assertIn(SPEC["headline"], original_app.read_text(encoding="utf-8"))
        self.assertIn(revision_spec()["headline"], changed_app.read_text(encoding="utf-8"))

    def test_source_aware_goal_uses_one_model_call_and_diff(self):
        original = self.original()
        with (patch("agentforge.workspace_policy.read", return_value={
            "website_enabled": True, "max_estimated_model_calls": 1,
        }), patch("agentforge.goal_preflight.require_ready")):
            request = webapp_feedback.request_revision(
                original["proposal_id"], original["sha256"],
                "Đổi màu chủ đạo sang xanh navy và viết lại tiêu đề.",
                brain_db_path=self.brain)
        self.assertEqual(request["status"], "PLAN_CREATED")
        goal = brain_store.get_goal(request["goal_id"], db_path=self.brain)
        self.assertEqual(goal["template"], "webapp.revision")
        self.assertEqual(goal["plan"][0]["skill_id"], "webapp.create")
        self.assertEqual(goal["plan"][0]["payload"]["source_sha256"], original["sha256"])
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"], db_path=self.brain)
        with patch("agentforge.model.generate_json", return_value=revision_spec()) as model:
            result = brain_runner.execute(
                goal["goal_id"], brain_db_path=self.brain, task_db_path=self.tasks,
                grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True)
            model.assert_called_once()
        self.assertEqual(result["status"], "SUCCEEDED", result)
        step = brain_store.get_goal(goal["goal_id"], db_path=self.brain)["steps"][0]
        task = task_history.get_task(step["child_task_id"], db_path=self.tasks)
        self.assertTrue(webapp_builder.compare(task["result"]["proposal_id"])["visible_change"])
        self.assertFalse(webapp_builder.PROJECTS.exists())

    def test_missing_provenance_and_invalid_feedback_rejected(self):
        original = self.original()
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaisesRegex(ValueError, "APP_REVISION_INVALID"):
                webapp_builder.propose(
                    "demo-revised", BRIEF,
                    source_proposal_id=original["proposal_id"],
                    revision_feedback="Đổi màu sang xanh")
            with self.assertRaises(ValueError):
                webapp_builder.propose(
                    "demo-revised", BRIEF,
                    source_proposal_id=original["proposal_id"],
                    source_sha256=original["sha256"],
                    revision_feedback="ngắn")
            model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
