"""Wave 6: immutable AI React code revisions, diff, rollback and Owner gates.

The model is mocked; real HTTP/session/CSRF, SHA, SQLite and source validation
run against temp directories. No generated React JS is executed on host.
"""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner, brain_store, webapp_builder, webapp_developer
from agentforge.features.webapps import revisions
from tests.test_webapp_developer_v42b import MODEL, APP, CSS, BRIEF
from tests.test_webapp_revision_http_v41 import WebappRevisionHttpTests

DEV = webapp_developer
NEW_CSS = CSS + "\nfooter { border-top: 2px solid navy; padding: 16px; }\n"
NEW_APP = APP.replace("Cửa hàng demo", "Cửa hàng demo mới")
FEEDBACK = "Thêm đường viền màu navy ở cuối trang, giữ nguyên giỏ hàng."
PATCH_CSS = {"title": "Cửa hàng React cập nhật",
             "summary": "Giỏ hàng giữ nguyên, thêm footer navy.",
             "changes": [{"path": "src/styles.css", "content": NEW_CSS}]}


class Wave6SourceRevisionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for obj, attr, value in (
            (DEV, "PROPOSALS", root / "react"),
            (DEV, "PROJECTS", root / "projects"),
            (webapp_builder, "PROPOSALS", root / "marketplace"),
            (webapp_builder, "PROJECTS", root / "projects"),
        ):
            p = patch.object(obj, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def create_root(self):
        with patch("agentforge.model.generate_json", return_value=MODEL):
            return DEV.propose("react-root", BRIEF)

    def revise(self, source, patch_value=None, slug="react-revised"):
        with patch("agentforge.model.generate_json",
                   return_value=PATCH_CSS if patch_value is None else patch_value) as model:
            receipt = DEV.propose(
                slug, BRIEF, source_proposal_id=source["proposal_id"],
                source_sha256=source["sha256"], revision_feedback=FEEDBACK)
            model.assert_called_once()
            self.assertEqual(model.call_args.args[1], revisions.EDIT_SCHEMA)
            self.assertEqual(model.call_args.kwargs["worker_id"], DEV.WORKER_ID)
            self.assertIn("EXISTING REACT SOURCE", model.call_args.args[0])
            source_block = model.call_args.args[0].rsplit(
                "EXISTING REACT SOURCE (UNTRUSTED DATA):", 1)[1].strip()
            self.assertEqual(json.loads(source_block)["src/App.jsx"], APP)
        return receipt

    def test_edit_preserves_untouched_source_and_builds_diff_with_sha(self):
        source = self.create_root()
        with patch("subprocess.run") as process:
            revised = self.revise(source)
            process.assert_not_called()
        self.assertNotEqual(revised["sha256"], source["sha256"])
        self.assertEqual(revised["changed_files"], ["src/styles.css"])
        self.assertFalse(DEV.PROJECTS.exists())
        root, _ = DEV._read_proposal(source["proposal_id"])
        doc, _ = DEV._read_proposal(revised["proposal_id"])
        original = {f["path"]: f["content"] for f in root["files"]}
        newer = {f["path"]: f["content"] for f in doc["files"]}
        self.assertEqual(newer["src/App.jsx"], original["src/App.jsx"])
        self.assertEqual(newer["src/styles.css"], NEW_CSS)
        self.assertEqual(original["src/styles.css"], CSS)
        # Trusted package identity is regenerated for the new slug; model does
        # not get to edit scripts/dependency versions or the lockfile contents.
        new_package = json.loads(newer["package.json"])
        old_package = json.loads(original["package.json"])
        for key in ("scripts", "dependencies", "devDependencies", "overrides"):
            self.assertEqual(new_package.get(key), old_package.get(key))
        self.assertEqual(new_package["name"], "@agentforge/react-revised")
        self.assertEqual(json.loads(newer["package-lock.json"])["packages"][""]["devDependencies"],
                         json.loads(original["package-lock.json"])["packages"][""]["devDependencies"])
        self.assertEqual(doc["revision"]["source_sha256"], source["sha256"])
        comparison = DEV.compare(revised["proposal_id"])
        self.assertEqual(comparison["changed_files"], ["src/styles.css"])
        self.assertIn("footer", comparison["diffs"][0]["diff"])
        self.assertEqual([v["proposal_id"] for v in comparison["versions"]],
                         [revised["proposal_id"], source["proposal_id"]])
        self.assertFalse(doc["execution_authorized"])

    def test_second_edit_and_verified_non_destructive_rollback(self):
        source = self.create_root()
        one = self.revise(source)
        two = self.revise(one, {
            "title": "Cửa hàng React cập nhật lần 2",
            "summary": "Sửa tên cửa hàng và giữ lại CSS.",
            "changes": [{"path": "src/App.jsx", "content": NEW_APP}],
        }, slug="react-revised-twice")
        result = DEV.compare(two["proposal_id"])
        self.assertEqual(len(result["versions"]), 3)
        self.assertEqual(result["changed_files"], ["src/App.jsx"])
        with self.assertRaises(PermissionError):
            DEV.rollback(two["proposal_id"], two["sha256"],
                         source["proposal_id"], source["sha256"])
        with patch("agentforge.model.generate_json") as model, patch("subprocess.run") as cmd:
            restored = DEV.rollback(
                two["proposal_id"], two["sha256"],
                source["proposal_id"], source["sha256"], confirm_restore=True)
            model.assert_not_called()
            cmd.assert_not_called()
        new_doc, _ = DEV._read_proposal(restored["proposal_id"])
        root_doc, _ = DEV._read_proposal(source["proposal_id"])
        for path in ("src/App.jsx", "src/styles.css"):
            self.assertEqual(next(f["content"] for f in new_doc["files"] if f["path"] == path),
                             next(f["content"] for f in root_doc["files"] if f["path"] == path))
        self.assertEqual(len(DEV.compare(restored["proposal_id"])["versions"]), 4)
        self.assertEqual(new_doc["rollback_target"]["sha256"], source["sha256"])
        self.assertFalse(DEV.PROJECTS.exists())
        with self.assertRaises(PermissionError):
            DEV.apply(restored["proposal_id"], sha256=restored["sha256"])
        saved = DEV.apply(restored["proposal_id"], sha256=restored["sha256"],
                          confirm_write=True)
        self.assertEqual(saved["status"], "FILES_WRITTEN_NOT_EXECUTED")
        self.assertTrue((DEV.PROJECTS / restored["project_slug"] / "src" / "App.jsx").is_file())
        self.assertFalse((DEV.PROJECTS / "react-root").exists())
        with self.assertRaises(FileExistsError):
            DEV.apply(restored["proposal_id"], sha256=restored["sha256"],
                      confirm_write=True)

    def test_rejects_noop_unsafe_patch_and_unapproved_paths_without_writes(self):
        source = self.create_root()
        invalid = [
            {**PATCH_CSS, "changes": [{"path": "src/styles.css", "content": CSS}]},
            {**PATCH_CSS, "changes": [{"path": "package.json", "content": NEW_CSS}]},
            {**PATCH_CSS, "changes": [{"path": "../secrets.js", "content": NEW_CSS}]},
            {**PATCH_CSS, "changes": [{"path": "src/App.jsx",
                                     "content": APP + "\nfetch('abc');"}]},
            {**PATCH_CSS, "changes": [{"path": "src/App.jsx",
                                     "content": "export default function"}]},
            {**PATCH_CSS, "changes": []},
        ]
        for ix, value in enumerate(invalid):
            with self.subTest(case=ix), patch("agentforge.model.generate_json",
                                                return_value=value):
                with self.assertRaises(ValueError):
                    DEV.propose("bad-" + str(ix), BRIEF,
                                source_proposal_id=source["proposal_id"],
                                source_sha256=source["sha256"],
                                revision_feedback=FEEDBACK)
        self.assertEqual(len(list(DEV.PROPOSALS.glob("*.json"))), 1)

    def test_rejects_stale_sha_tampered_parent_invalid_rollback_lineage(self):
        source = self.create_root()
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises(PermissionError):
                DEV.propose("new-app", BRIEF,
                            source_proposal_id=source["proposal_id"],
                            source_sha256="0" * 64, revision_feedback=FEEDBACK)
            model.assert_not_called()
        child = self.revise(source)
        with self.assertRaises(PermissionError):
            DEV.rollback(child["proposal_id"], child["sha256"],
                         child["proposal_id"], child["sha256"], confirm_restore=True)
        with self.assertRaises(PermissionError):
            DEV.rollback(child["proposal_id"], "f" * 64,
                         source["proposal_id"], source["sha256"], confirm_restore=True)
        path = DEV._proposal_path(child["proposal_id"])
        record = json.loads(path.read_text(encoding="utf-8"))
        record["revision"]["source_sha256"] = "0" * 64
        # Even recomputing the plain JSON digest cannot forge provenance.
        record["sha256"] = DEV._digest(
            record["project_slug"], record["brief"], record["title"],
            record["summary"], record["files"],
            revision=record["revision"], architecture=record.get("architecture"))
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(PermissionError):
            DEV._read_proposal(child["proposal_id"])
        self.assertFalse(DEV.PROJECTS.exists())

    def test_approved_goal_dispatches_one_source_edit_after_owner_permission(self):
        from agentforge import brain_runner
        source = self.create_root()
        inputs = {"slug": "goal-react-edited", "brief": BRIEF,
                  "source_proposal_id": source["proposal_id"],
                  "source_sha256": source["sha256"],
                  "revision_feedback": FEEDBACK}
        root = DEV.PROPOSALS.parent
        goals, tasks = root / "brain.sqlite3", root / "tasks.sqlite3"
        goal = brain_planner.propose(
            "Sửa ứng dụng React demo", "webapp.source_revision", inputs,
            max_model_calls=1, max_external_runs=0, db_path=goals)
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises(brain_store.BrainError):
                brain_runner.execute(goal["goal_id"],
                                     brain_db_path=goals, task_db_path=tasks)
            model.assert_not_called()
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"], db_path=goals)
        with patch("agentforge.model.generate_json", return_value=PATCH_CSS) as model, \
             patch("subprocess.run") as process:
            result = brain_runner.execute(
                goal["goal_id"], brain_db_path=goals, task_db_path=tasks,
                grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True)
            model.assert_called_once()
            process.assert_not_called()
        self.assertEqual(result["status"], "SUCCEEDED", result)
        proposals = sorted(DEV.PROPOSALS.glob("*.json"))
        self.assertEqual(len(proposals), 2)
        latest = next(json.loads(path.read_text(encoding="utf-8"))
                      for path in proposals if json.loads(path.read_text(encoding="utf-8"))
                      .get("revision") is not None)
        self.assertEqual(latest["revision"]["source_sha256"], source["sha256"])

    def test_architect_lineage_survives_source_revision_and_static_qa(self):
        from agentforge.features.webapps import architect, static_qa
        from tests.test_v5_company import ARCH
        root = DEV.PROPOSALS.parent
        with patch.object(architect, "ARCHITECTURES", root / "architect"), \
             patch.object(static_qa, "REPORTS", root / "qa"), \
             patch.object(architect, "require_worker_model"):
            with patch("agentforge.model.generate_json", return_value=ARCH):
                original_arch = architect.propose("react-root", BRIEF)
            with patch("agentforge.model.generate_json", return_value=MODEL):
                parent = DEV.propose(
                    "react-root", BRIEF,
                    architecture_id=original_arch["architecture_id"],
                    architecture_sha=original_arch["architecture_sha"])
            child = self.revise(parent)
            signed, _ = DEV._read_proposal(child["proposal_id"])
            self.assertEqual(signed["architecture"], {
                "architecture_id": original_arch["architecture_id"],
                "architecture_sha": original_arch["architecture_sha"]})
            report = static_qa.audit(child["proposal_id"], child["sha256"])
            self.assertEqual(report["status"], "PASS_STATIC_ONLY")
            self.assertFalse(report["browser_verified"])
            self.assertFalse(report["build_verified"])

    def test_model_revision_goal_is_one_gated_webapp_develop_call(self):
        source = self.create_root()
        from agentforge.core import brain_planner as planner
        inputs = {"slug": "revision-a", "brief": BRIEF,
                  "source_proposal_id": source["proposal_id"],
                  "source_sha256": source["sha256"],
                  "revision_feedback": FEEDBACK}
        steps = planner.make_plan("webapp.source_revision", inputs, max_model_calls=1)
        self.assertEqual([x["skill_id"] for x in steps], ["webapp.develop"])
        self.assertIn("source_proposal_id", steps[0]["payload"])
        with self.assertRaises(brain_store.BrainError):
            planner.make_plan("webapp.source_revision", inputs, max_model_calls=0)


class Wave6HttpTests(unittest.TestCase):
    def setUp(self):
        fixture = WebappRevisionHttpTests("test_revision_endpoint_creates_goal_but_does_not_dispatch_model")
        fixture.setUp()
        self.fixture = fixture
        self.addCleanup(fixture.doCleanups)
        self.root = Path(fixture.brain).parent
        for obj, attr, value in (
            (DEV, "PROPOSALS", self.root / "react-proposals"),
            (DEV, "PROJECTS", self.root / "react-workspace"),
        ):
            p = patch.object(obj, attr, value)
            p.start()
            self.addCleanup(p.stop)
        with patch("agentforge.model.generate_json", return_value=MODEL):
            self.source = DEV.propose("react-root", BRIEF)

    def test_real_owner_session_review_revision_and_rollback(self):
        api = self.fixture
        pid = self.source["proposal_id"]
        req = "/api/webapps/" + pid
        self.assertEqual(api.req("GET", req)[0], 401)
        api.login()
        status, body, _ = api.req("GET", req)
        self.assertEqual(status, 200)
        self.assertFalse(body["comparison"]["revision"])
        self.assertTrue(body["ai_code_experimental"])
        payload = {"ack": "REQUEST_REVISION", "sha256": self.source["sha256"],
                   "feedback": FEEDBACK}
        self.assertEqual(api.req("POST", req + "/revision", payload, csrf=False)[0], 403)
        with patch("agentforge.model.generate_json") as model:
            code, response, _ = api.req("POST", req + "/revision", payload)
            self.assertEqual(code, 200, response)
            model.assert_not_called()
        goal = brain_store.get_goal(response["goal_id"], db_path=api.brain)
        self.assertEqual(goal["template"], "webapp.source_revision")
        self.assertEqual(goal["plan"][0]["skill_id"], "webapp.develop")
        with patch("agentforge.model.generate_json", return_value=PATCH_CSS):
            child = DEV.propose(
                "react-edited", BRIEF, source_proposal_id=pid,
                source_sha256=self.source["sha256"], revision_feedback=FEEDBACK)
        rollback_path = "/api/webapps/" + child["proposal_id"] + "/rollback"
        target = {"ack": "RESTORE_REACT_VERSION", "sha256": child["sha256"],
                  "target_proposal_id": pid, "target_sha256": self.source["sha256"]}
        self.assertEqual(api.req("POST", rollback_path, target)[0], 400)
        code, doc, _ = api.req("GET", "/api/webapps/" + child["proposal_id"])
        self.assertEqual(code, 200)
        self.assertEqual(doc["comparison"]["changed_files"], ["src/styles.css"])
        self.assertEqual(api.req("POST", rollback_path, {**target, "ack": "no"})[0], 400)
        self.assertEqual(api.req("POST", rollback_path, target, csrf=False)[0], 403)
        self.assertEqual(api.req("POST", rollback_path, target)[0], 200)
        self.assertEqual(api.req("POST", rollback_path, {**target, "sha256":"0"*64})[0], 400)


if __name__ == "__main__":
    unittest.main()
