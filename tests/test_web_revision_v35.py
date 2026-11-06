"""Website revision regression: original SHA + full feedback + visible changes.

Uses a mocked model, isolated SQLite/files; never opens a browser or network.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner, brain_runner, brain_store, task_history
from agentforge import product_builder as builder
from agentforge import website_feedback
from agentforge.domains.websites.preview import from_proposal
from agentforge.domains.websites.structured_builder import render, requested_design

COPY = {
    "brand": "Studio Giấc Ngủ",
    "headline": "Chọn nệm đúng với nhu cầu",
    "subtitle": "Khám phá lựa chọn nệm phù hợp cho ngôi nhà của bạn.",
    "introduction": "Trang tư vấn lựa chọn nệm, chưa xác nhận thông tin sản phẩm.",
    "highlights": [
        {"title": "Tư vấn", "description": "Tìm hiểu nhu cầu trước khi chọn nệm."},
        {"title": "Trải nghiệm", "description": "Ưu tiên cảm giác và không gian phòng ngủ."},
    ],
    "call_to_action": "Nhận tư vấn về lựa chọn nệm",
}
BRIEF = ("Tạo website giới thiệu dịch vụ tư vấn nệm cao cấp, giao diện hiện đại "
         "với số hotline 0879547988 và chính sách minh bạch.")


class WebsiteRevisionV35Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.brain = self.root / "brain.sqlite3"
        self.tasks = self.root / "tasks.sqlite3"
        for name, value in [
            ("ROOT", self.root),
            ("WORKSPACE", self.root / "workspace"),
            ("PRODUCTS", self.root / "workspace" / "products"),
            ("PROPOSALS", self.root / "data" / "company" / "product_builder" / "proposals"),
        ]:
            p = patch.object(builder, name, value)
            p.start()
            self.addCleanup(p.stop)

    def original(self):
        with patch("agentforge.model.generate_json", return_value=COPY) as model:
            first = builder.propose("nem-original", BRIEF)
            model.assert_called_once()
        return first

    def test_style_variations_are_safe_and_not_identical(self):
        forest = render(COPY)
        ocean = render(COPY, theme="ocean", layout="centered")
        self.assertNotEqual(forest, ocean)
        self.assertIn('data-af-theme="ocean"', ocean)
        self.assertIn('data-af-layout="centered"', ocean)
        self.assertIn("grid-template-columns:1fr", ocean)
        self.assertNotIn("https://", ocean)
        from agentforge.product_quality import analyze
        self.assertNotEqual(analyze(ocean)["status"], "FAIL")
        self.assertEqual(requested_design("Đổi sang màu xanh dương, căn giữa phần hero"),
                         {"theme": "ocean", "layout": "centered"})

    def test_revision_has_complete_source_and_feedback_through_goal_to_preview(self):
        original = self.original()
        source_before = Path(original["proposal_path"]).read_bytes()
        feedback = "Đổi giao diện sang màu xanh dương, căn giữa phần hero; giữ nội dung chính."
        with (patch("agentforge.workspace_policy.read", return_value={
            "website_enabled": True, "max_estimated_model_calls": 1
        }), patch("agentforge.goal_preflight.require_ready")):
            submitted = website_feedback.request_revision(
                original["proposal_id"], original["sha256"], feedback,
                brain_db_path=self.brain)
        self.assertEqual(submitted["status"], "PLAN_CREATED")
        goal = brain_store.get_goal(submitted["goal_id"], db_path=self.brain)
        payload = goal["plan"][0]["payload"]
        self.assertEqual(payload["revision_feedback"], feedback)
        self.assertEqual(payload["source_proposal_id"], original["proposal_id"])
        self.assertEqual(payload["source_sha256"], original["sha256"])
        self.assertEqual(payload["brief"], BRIEF)
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"], db_path=self.brain)
        with patch("agentforge.model.generate_json", return_value=COPY) as model:
            result = brain_runner.execute(
                goal["goal_id"], brain_db_path=self.brain, task_db_path=self.tasks,
                grants=("model.invoke", "workspace.propose"), confirm_model_call=True)
            model.assert_called_once()
            prompt = model.call_args.args[0]
            self.assertIn(feedback, prompt)
            self.assertIn("Chọn nệm đúng với nhu cầu", prompt)
            self.assertIn("PREVIOUS VISIBLE WEBSITE TEXT", prompt)
        self.assertEqual(result["status"], "SUCCEEDED", result)
        step = brain_store.get_goal(goal["goal_id"], db_path=self.brain)["steps"][0]
        task = task_history.get_task(step["child_task_id"], db_path=self.tasks)
        receipt = task["result"]
        html = from_proposal(receipt["proposal_id"]).decode("utf-8")
        self.assertIn('data-af-theme="ocean"', html)
        self.assertIn('data-af-layout="centered"', html)
        self.assertIn('href="tel:0879547988"', html)
        self.assertNotEqual(
            html, from_proposal(original["proposal_id"]).decode("utf-8"))
        self.assertEqual(Path(original["proposal_path"]).read_bytes(), source_before)
        self.assertFalse(builder.PRODUCTS.exists())

    def test_unchanged_output_is_rejected_without_new_proposal(self):
        original = self.original()
        with patch("agentforge.model.generate_json", return_value=COPY) as model:
            with self.assertRaisesRegex(ValueError, "REVISION_NO_CHANGE"):
                builder.propose(
                    "nem-revision", BRIEF,
                    source_proposal_id=original["proposal_id"],
                    source_sha256=original["sha256"],
                    revision_feedback="Đổi tiêu đề thành nội dung khác dễ hiểu hơn.")
            model.assert_called_once()
        self.assertEqual(len(list(builder.PROPOSALS.glob("*.json"))), 1)

    def test_old_v34_template_metadata_difference_is_not_a_real_edit(self):
        first = self.original()
        path = Path(first["proposal_path"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        source = doc["files"][0]["content"]
        old_style_marker = ' data-af-theme="forest" data-af-layout="split"'
        self.assertIn(old_style_marker, source)
        doc["files"][0]["content"] = source.replace(old_style_marker, "")
        doc["sha256"] = builder._digest(
            doc["project_slug"], doc["brief"],
            {"summary": doc["summary"], "files": doc["files"]})
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with patch("agentforge.model.generate_json", return_value=COPY) as model:
            with self.assertRaisesRegex(ValueError, "REVISION_NO_CHANGE"):
                builder.propose(
                    "nem-revision", BRIEF,
                    source_proposal_id=first["proposal_id"],
                    source_sha256=doc["sha256"],
                    revision_feedback="Hãy sửa phần tiêu đề cho khác và hấp dẫn hơn.")
            model.assert_called_once()
        self.assertEqual(len(list(builder.PROPOSALS.glob("*.json"))), 1)

    def test_stale_sha_denied_before_model_call(self):
        original = self.original()
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises(PermissionError):
                builder.propose(
                    "nem-revision", BRIEF,
                    source_proposal_id=original["proposal_id"],
                    source_sha256="0" * 64,
                    revision_feedback="Thay đổi bố cục sang kiểu editorial.")
            model.assert_not_called()

    def test_large_brief_and_feedback_not_truncated(self):
        original = self.original()
        long_feedback = "Chỉnh sửa nội dung ưu tiên trải nghiệm mua sắm. " + "chi tiết " * 220
        self.assertGreater(len(long_feedback), 360)
        with patch("agentforge.model.generate_json", return_value={**COPY, "headline": "Khám phá nệm mới"}) as model:
            builder.propose(
                "nem-revision", BRIEF,
                source_proposal_id=original["proposal_id"],
                source_sha256=original["sha256"],
                revision_feedback=long_feedback)
            self.assertIn(long_feedback.strip(), model.call_args.args[0])
        self.assertEqual(len(list(builder.PROPOSALS.glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
