"""S4 -> S1 -> model -> SHA proposal -> preview with no real model/network."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner, brain_runner, brain_store, task_history
from agentforge import product_builder as builder
from agentforge.domains.websites.preview import from_proposal

CONTENT = {
    "brand": "Studio Nệm Việt",
    "headline": "Không gian ngủ được chăm chút",
    "subtitle": "Tư vấn lựa chọn nệm theo nhu cầu và không gian sống.",
    "introduction": "Đây là trang mẫu giới thiệu dịch vụ tư vấn. Chi tiết sản phẩm cần được chủ dự án xác minh.",
    "highlights": [
        {"title": "Tư vấn nhu cầu", "description": "Lắng nghe thói quen ngủ của bạn."},
        {"title": "Tối ưu không gian", "description": "Gợi ý lựa chọn phù hợp với phòng ngủ."},
        {"title": "Liên hệ trực tiếp", "description": "Trao đổi trước khi đặt hàng."},
    ],
    "call_to_action": "Trao đổi về chiếc nệm phù hợp",
}


class TestWebGoalV34(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.brain = root / "brain.sqlite3"
        self.tasks = root / "tasks.sqlite3"
        self.patchers = [
            patch.object(builder, "ROOT", root),
            patch.object(builder, "WORKSPACE", root / "workspace"),
            patch.object(builder, "PRODUCTS", root / "workspace" / "products"),
            patch.object(builder, "PROPOSALS", root / "data" / "company" / "product_builder" / "proposals"),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in reversed(self.patchers):
            item.stop()
        self.tmp.cleanup()

    def _goal(self):
        brief = "Làm website giới thiệu nệm, hỗ trợ điện thoại, hotline 0879547988, giao diện hiện đại."
        goal = brain_planner.propose(
            "Tư vấn nệm", "website.draft",
            {"slug": "nem-thu-nghiem", "brief": brief},
            max_model_calls=1, db_path=self.brain)
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"], db_path=self.brain)
        return goal

    def _execute(self, goal, **kwargs):
        return brain_runner.execute(
            goal["goal_id"], brain_db_path=self.brain,
            task_db_path=self.tasks, **kwargs)

    def test_waiting_gate_resume_one_model_call_and_preview(self):
        goal = self._goal()
        with patch("agentforge.model.generate_json") as model:
            waiting = self._execute(goal)
            model.assert_not_called()
        self.assertEqual(waiting["status"], "WAITING_APPROVAL")
        self.assertIn("model.invoke", waiting["missing"])
        with patch("agentforge.model.generate_json", return_value=CONTENT) as model:
            completed = self._execute(
                goal, grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True)
            model.assert_called_once()
        self.assertEqual(completed["status"], "SUCCEEDED")
        self.assertFalse(builder.PRODUCTS.exists())
        stored = brain_store.get_goal(goal["goal_id"], db_path=self.brain)
        self.assertEqual(len(stored["steps"]), 1)
        child = task_history.get_task(stored["steps"][0]["child_task_id"], db_path=self.tasks)
        self.assertEqual(child["status"], "SUCCEEDED")
        proposal = child["result"]
        self.assertRegex(proposal["sha256"], r"^[0-9a-f]{64}$")
        page = from_proposal(proposal["proposal_id"]).decode("utf-8")
        self.assertIn("Studio Nệm Việt", page)
        self.assertIn('href="tel:0879547988"', page)
        self.assertIn("Content-Security-Policy", page)
        self.assertNotIn("https://", page)
        with self.assertRaises(Exception):
            self._execute(goal, grants=("model.invoke", "workspace.propose"),
                          confirm_model_call=True)

    def test_invalid_copy_fails_without_proposal_or_second_model_call(self):
        goal = self._goal()
        bad = dict(CONTENT)
        bad["highlights"] = []
        with patch("agentforge.model.generate_json", return_value=bad) as model:
            done = self._execute(goal, grants=("model.invoke", "workspace.propose"),
                                 confirm_model_call=True)
            model.assert_called_once()
        self.assertEqual(done["status"], "FAILED")
        self.assertFalse(builder.PROPOSALS.exists())
        self.assertFalse(builder.PRODUCTS.exists())


if __name__ == "__main__":
    unittest.main()
