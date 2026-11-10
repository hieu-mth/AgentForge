"""V5 signed four-stage company Goal: one model confirmation per action."""
from copy import deepcopy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import (
    brain_planner, brain_runner, brain_store, prompt_intake,
    task_history, webapp_builder, webapp_developer,
)
from agentforge.domains.webapps import architect, static_qa, reviewer
from agentforge.ai import role_routing
from tests.test_webapp_developer_v42b import MODEL

BRIEF = ("AI Company V5: tạo web app React quản lý catalog demo với tìm kiếm,"
         " bộ lọc và giỏ hàng local hoạt động, không API bên ngoài.")
ARCH = {
    "title": "Ứng dụng mua sắm thử nghiệm",
    "audience": "Người dùng cần thử các thao tác mua sắm demo",
    "purpose": "Tìm kiếm, xem hàng và tạo giỏ hàng local",
    "ui_sections": ["Header có tìm kiếm", "Sản phẩm trong lưới", "Giỏ hàng demo"],
    "user_flows": ["Nhập tên sản phẩm và lọc kết quả",
                   "Thêm sản phẩm vào giỏ và tăng giảm số lượng"],
    "local_data": ["Tám sản phẩm demo có giá và danh mục"],
    "constraints": ["Không đăng nhập hay thanh toán thật",
                    "Không kết nối mạng hoặc lấy dữ liệu khách hàng"],
}
REVIEW = {
    "recommendation":"MANUAL_REVIEW",
    "summary":"Cần kiểm tra tương tác với trình duyệt trước khi nghiệm thu.",
    "missing_features":["Chưa chứng minh tìm kiếm thực sự hoạt động"],
    "risks":["Chưa build hoặc test trình duyệt"],
}


class V5CompanyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.brain = root / "goals.db"
        self.tasks = root / "tasks.db"
        for module, name, value in [
            (architect, "ARCHITECTURES", root / "architect"),
            (webapp_developer, "PROPOSALS", root / "developer"),
            (webapp_developer, "PROJECTS", root / "projects"),
            (webapp_builder, "PROJECTS", root / "projects"),
            (webapp_builder, "PROPOSALS", root / "marketplace"),
            (static_qa, "REPORTS", root / "qa"),
            (reviewer, "REPORTS", root / "reviewer"),
        ]:
            p = patch.object(module,name,value)
            p.start()
            self.addCleanup(p.stop)
        env = patch.dict(os.environ,{"AGENTFORGE_MODEL_REF":"local_primary",
                                    "AGENTFORGE_CLOUD_MODEL_CONSENT":""})
        env.start()
        self.addCleanup(env.stop)

    def plan(self):
        goal = brain_planner.propose("V5 company test","webapp.company",
            {"slug":"v5-marketplace","brief":BRIEF},max_model_calls=3,
            max_external_runs=0,db_path=self.brain)
        return goal

    def test_fixed_four_role_plan_three_calls_and_zero_external_processes(self):
        plan = brain_planner.make_plan("webapp.company",
            {"slug":"v5-marketplace","brief":BRIEF},max_model_calls=3)
        self.assertEqual([x["skill_id"] for x in plan],
            ["webapp.architect","webapp.develop","webapp.audit","webapp.review"])
        self.assertEqual(sum(x["estimated_model_calls"] for x in plan),3)
        self.assertFalse(any(x["external_process"] for x in plan))
        self.assertEqual(plan[1]["payload"]["architecture_id"],
                         {"from_step":0,"field":"architecture_id"})
        self.assertEqual(plan[2]["payload"]["sha256"],
                         {"from_step":1,"field":"sha256"})
        self.assertEqual(plan[3]["payload"]["qa_report_sha"],
                         {"from_step":2,"field":"qa_report_sha"})
        with self.assertRaises(brain_store.BrainError):
            brain_planner.make_plan("webapp.company",
                {"slug":"v5-marketplace","brief":BRIEF},max_model_calls=2)
        with self.assertRaises(brain_store.BrainError):
            brain_planner.make_plan("webapp.company",
                {"slug":"v5-marketplace","brief":BRIEF,"external":True},
                max_model_calls=3)

    def test_architect_source_is_immutable_and_sha_checked(self):
        with patch("agentforge.model.generate_json",return_value=ARCH) as model:
            receipt=architect.propose("v5-marketplace",BRIEF)
            model.assert_called_once()
        source=architect.read(receipt["architecture_id"],receipt["architecture_sha"])
        self.assertEqual(source["spec"],ARCH)
        path=architect._path(receipt["architecture_id"])
        original=json.loads(path.read_text(encoding="utf-8"))
        original["spec"]["title"]="Bị thay đổi"
        path.write_text(json.dumps(original,ensure_ascii=False),encoding="utf-8")
        with self.assertRaises(PermissionError):
            architect.read(receipt["architecture_id"],receipt["architecture_sha"])

    def test_v5_pipeline_requires_three_separate_owner_actions(self):
        goal=self.plan()
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises(brain_store.BrainError):
                brain_runner.execute(goal["goal_id"],brain_db_path=self.brain,
                                     task_db_path=self.tasks)
            model.assert_not_called()
        brain_store.approve_goal(goal["goal_id"],goal["plan_sha256"],
                                db_path=self.brain)
        with patch("agentforge.model.generate_json",
                   side_effect=[ARCH, MODEL, REVIEW]) as model, \
             patch("subprocess.run") as process:
            first=brain_runner.execute(goal["goal_id"],brain_db_path=self.brain,
                task_db_path=self.tasks,
                grants=("model.invoke","workspace.propose"),
                confirm_model_call=True)
            self.assertEqual(first["status"],"WAITING_APPROVAL",first)
            self.assertEqual(first["waiting_step"],1)
            self.assertEqual(model.call_count,1)
            second=brain_runner.execute(goal["goal_id"],brain_db_path=self.brain,
                task_db_path=self.tasks,
                grants=("model.invoke","workspace.propose"),
                confirm_model_call=True)
            self.assertEqual(second["status"],"WAITING_APPROVAL",second)
            self.assertEqual(second["waiting_step"],3)
            self.assertEqual(model.call_count,2)
            third=brain_runner.execute(goal["goal_id"],brain_db_path=self.brain,
                task_db_path=self.tasks,
                grants=("model.invoke","workspace.propose"),
                confirm_model_call=True)
            self.assertEqual(third["status"],"SUCCEEDED",third)
            self.assertEqual(third["step_count"],4)
            self.assertEqual(model.call_count,3)
            process.assert_not_called()
        steps=brain_store.get_goal(goal["goal_id"],db_path=self.brain)["steps"]
        self.assertEqual(len(steps),4)
        self.assertTrue(all(x["status"]=="SUCCEEDED" for x in steps))
        result=[task_history.get_task(x["child_task_id"],db_path=self.tasks)["result"]
                for x in steps]
        self.assertEqual(result[2]["status"],"PASS_STATIC_ONLY")
        self.assertFalse(result[2]["build_verified"])
        self.assertFalse(result[2]["browser_verified"])
        self.assertEqual(result[3]["status"],"REVIEWED_NOT_APPROVED")
        self.assertFalse(result[3]["execution_authorized"])
        self.assertFalse(webapp_developer.PROJECTS.exists())
        qa=static_qa.read(result[2]["qa_report_id"],result[2]["qa_report_sha"])
        report=reviewer.read(result[3]["review_id"],result[3]["review_sha"])
        self.assertEqual(qa["proposal_id"],result[1]["proposal_id"])
        self.assertEqual(report["proposal_id"],result[1]["proposal_id"])
        self.assertEqual(report["assessment"],REVIEW)

    def test_failed_architect_can_retry_same_goal_without_replaying_success(self):
        goal = self.plan()
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"],
                                db_path=self.brain)
        with patch("agentforge.model.generate_json",
                   side_effect=ValueError("ARCHITECTURE_INVALID: title")) as model:
            failed = brain_runner.execute(
                goal["goal_id"], brain_db_path=self.brain, task_db_path=self.tasks,
                grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True)
            model.assert_called_once()
        self.assertEqual(failed["status"], "FAILED", failed)
        before = brain_store.get_goal(goal["goal_id"], db_path=self.brain)
        self.assertEqual(before["current_step"], 0)
        self.assertEqual(before["steps"][0]["status"], "FAILED")
        failed_id = before["steps"][0]["child_task_id"]
        with self.assertRaises(brain_store.BrainError):
            brain_runner.retry_failed_step(
                goal["goal_id"], "0"*64, failed_id,
                brain_db_path=self.brain, task_db_path=self.tasks)
        with self.assertRaises(brain_store.BrainError):
            brain_runner.retry_failed_step(
                goal["goal_id"], goal["plan_sha256"], "f"*32,
                brain_db_path=self.brain, task_db_path=self.tasks)
        armed = brain_runner.retry_failed_step(
            goal["goal_id"], goal["plan_sha256"], failed_id,
            brain_db_path=self.brain, task_db_path=self.tasks)
        self.assertEqual(armed["status"], "APPROVED")
        self.assertFalse(armed["model_invoked"])
        rearmed = brain_store.get_goal(goal["goal_id"], db_path=self.brain)
        self.assertFalse(rearmed["steps"])
        self.assertEqual(rearmed["current_step"], 0)
        self.assertTrue(any(e["name"] == "STEP_RETRY_ARMED" and
                            e["detail"]["previous_task_id"] == failed_id
                            for e in rearmed["events"]))
        with patch("agentforge.model.generate_json", return_value=ARCH) as model:
            resumed = brain_runner.execute(
                goal["goal_id"], brain_db_path=self.brain, task_db_path=self.tasks,
                grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True)
            model.assert_called_once()
        self.assertEqual(resumed["status"], "WAITING_APPROVAL")
        current = brain_store.get_goal(goal["goal_id"], db_path=self.brain)
        self.assertEqual(current["current_step"], 1)
        self.assertNotEqual(current["steps"][0]["child_task_id"], failed_id)
        self.assertEqual(task_history.get_task(failed_id, db_path=self.tasks)["status"],
                         "FAILED")
        with self.assertRaises(brain_store.BrainError):
            brain_runner.retry_failed_step(
                goal["goal_id"], goal["plan_sha256"], failed_id,
                brain_db_path=self.brain, task_db_path=self.tasks)

    def test_interrupted_goal_is_never_retryable(self):
        goal = self.plan()
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"],
                                db_path=self.brain)
        brain_store.change_state(goal["goal_id"], "INTERRUPTED",
                                 expected="APPROVED", db_path=self.brain)
        with self.assertRaises(brain_store.BrainError):
            brain_runner.retry_failed_step(
                goal["goal_id"], goal["plan_sha256"], "f"*32,
                brain_db_path=self.brain, task_db_path=self.tasks)

    def test_stale_architect_binding_aborts_before_model(self):
        with patch("agentforge.model.generate_json",return_value=ARCH):
            arch=architect.propose("v5-marketplace",BRIEF)
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises(PermissionError):
                webapp_developer.propose("v5-marketplace",BRIEF,
                    architecture_id=arch["architecture_id"],
                    architecture_sha="0"*64)
            model.assert_not_called()

    def test_review_requires_static_qa_and_architect_lineage(self):
        with patch("agentforge.model.generate_json",return_value=ARCH):
            arch=architect.propose("v5-marketplace",BRIEF)
        with patch("agentforge.model.generate_json",return_value=MODEL):
            app=webapp_developer.propose("v5-marketplace",BRIEF,
                architecture_id=arch["architecture_id"],
                architecture_sha=arch["architecture_sha"])
        qa=static_qa.audit(app["proposal_id"],app["sha256"])
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises((ValueError,PermissionError)):
                reviewer.review(arch["architecture_id"],arch["architecture_sha"],
                    app["proposal_id"],app["sha256"],
                    qa["qa_report_id"],"0"*64)
            model.assert_not_called()
        self.assertEqual(qa["status"],"PASS_STATIC_ONLY")

    def test_v5_intake_requires_explicit_3_call_budget_and_owner_policy(self):
        from agentforge import workspace_policy
        with patch("agentforge.workspace_policy.read",return_value={
            "website_enabled":True,"storyboard_enabled":True,
            "max_estimated_model_calls":3}):
            with self.assertRaises(ValueError):
                prompt_intake.plan_request(BRIEF,max_model_calls=1,
                                           brain_db_path=self.brain)
            planned=prompt_intake.plan_request(BRIEF,max_model_calls=3,
                                               brain_db_path=self.brain)
        self.assertEqual(planned["template"],"webapp.company")
        self.assertEqual(planned["status"],"PLAN_CREATED")
        self.assertFalse(planned["model_dispatched"])
        goal=brain_store.get_goal(planned["goal_id"],db_path=self.brain)
        self.assertEqual(goal["inputs"]["_limits"]["max_model_calls"],3)


if __name__=="__main__":
    unittest.main()
