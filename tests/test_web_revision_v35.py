"""Source-aware revisions preserve signed originals and change visible design."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_runner, brain_store, task_history
from agentforge import product_builder as builder, website_feedback
from agentforge.domains.websites.preview import from_proposal
from agentforge.domains.websites.structured_builder import render as legacy_render, requested_design
from tests.designer_fixture import DESIGN, revised_design

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
        with patch("agentforge.model.generate_json", return_value=DESIGN) as model:
            first = builder.propose("nem-original", BRIEF)
            model.assert_called_once()
        return first

    def test_v35_legacy_style_variations_still_render_safely(self):
        copy = {
            "brand": "Studio Nệm", "headline": "Giấc ngủ phù hợp",
            "subtitle": "Tư vấn theo nhu cầu", "introduction": "Nội dung mẫu",
            "highlights": [{"title": "Tư vấn", "description": "Theo nhu cầu"},
                           {"title": "Không gian", "description": "Theo phòng ngủ"}],
            "call_to_action": "Nhận tư vấn",
        }
        forest = legacy_render(copy)
        ocean = legacy_render(copy, theme="ocean", layout="centered")
        self.assertNotEqual(forest, ocean)
        self.assertIn('data-af-theme="ocean"', ocean)
        self.assertIn("grid-template-columns:1fr", ocean)
        self.assertEqual(requested_design("Đổi từ xanh rêu sang xanh dương, căn giữa hero"),
                         {"theme": "ocean", "layout": "centered"})

    def test_revision_preserves_source_and_feedback_through_goal_to_preview(self):
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
        with patch("agentforge.model.generate_json", return_value=revised_design()) as model:
            result = brain_runner.execute(
                goal["goal_id"], brain_db_path=self.brain, task_db_path=self.tasks,
                grants=("model.invoke", "workspace.propose"), confirm_model_call=True)
            model.assert_called_once()
            prompt = model.call_args.args[0]
            self.assertIn(feedback, prompt)
            self.assertIn(DESIGN["hero"]["headline"], prompt)
            self.assertIn("PRIOR DESIGN STRUCTURE", prompt)
        self.assertEqual(result["status"], "SUCCEEDED", result)
        step = brain_store.get_goal(goal["goal_id"], db_path=self.brain)["steps"][0]
        task = task_history.get_task(step["child_task_id"], db_path=self.tasks)
        receipt = task["result"]
        html = from_proposal(receipt["proposal_id"]).decode("utf-8")
        self.assertIn('--accent:#285baa', html)
        self.assertIn('hero-centered', html)
        self.assertIn('href="tel:0879547988"', html)
        self.assertIn(revised_design()["hero"]["headline"], html)
        self.assertNotEqual(html, from_proposal(original["proposal_id"]).decode("utf-8"))
        self.assertEqual(Path(original["proposal_path"]).read_bytes(), source_before)
        self.assertFalse(builder.PRODUCTS.exists())

    def test_identical_design_rejected_without_new_proposal(self):
        original = self.original()
        with patch("agentforge.model.generate_json", return_value=DESIGN) as model:
            with self.assertRaisesRegex(ValueError, "REVISION_NO_CHANGE"):
                builder.propose(
                    "nem-revision", BRIEF, source_proposal_id=original["proposal_id"],
                    source_sha256=original["sha256"],
                    revision_feedback="Đổi tiêu đề thành nội dung khác dễ hiểu hơn.")
            model.assert_called_once()
        self.assertEqual(len(list(builder.PROPOSALS.glob("*.json"))), 1)

    def test_v34_legacy_proposal_can_be_upgraded_without_source_mutation(self):
        old = {
            "brand": "Studio Nệm", "headline": "Chọn nệm theo nhu cầu",
            "subtitle": "Tư vấn trực tiếp", "introduction": "Tư vấn trước khi mua.",
            "highlights": [{"title": "Nhu cầu", "description": "Lắng nghe."},
                           {"title": "Không gian", "description": "Bố trí."}],
            "call_to_action": "Trao đổi nhu cầu",
        }
        html = legacy_render(old)
        source = builder.propose(
            "legacy-original", BRIEF,
            model_client=lambda *_args, **_kwargs: {
                "summary": "Original local website draft for revision",
                "files": [{"path": "index.html", "content": html}],
            })
        with patch("agentforge.model.generate_json", return_value=revised_design()) as model:
            updated = builder.propose(
                "nem-revision", BRIEF, source_proposal_id=source["proposal_id"],
                source_sha256=source["sha256"],
                revision_feedback="Thay đổi giao diện theo hướng editorial mới.")
            model.assert_called_once()
        page = from_proposal(updated["proposal_id"]).decode("utf-8")
        self.assertIn('data-af-version="designer-v1"', page)
        self.assertIn('section--faq', page)
        self.assertEqual(len(builder._read_proposal(source["proposal_id"])[0]["files"]), 1)

    def test_stale_sha_denied_before_model_call(self):
        original = self.original()
        with patch("agentforge.model.generate_json") as model:
            with self.assertRaises(PermissionError):
                builder.propose(
                    "nem-revision", BRIEF, source_proposal_id=original["proposal_id"],
                    source_sha256="0" * 64,
                    revision_feedback="Thay đổi bố cục sang kiểu editorial.")
            model.assert_not_called()

    def test_long_feedback_not_truncated(self):
        original = self.original()
        long_feedback = "Chỉnh sửa nội dung ưu tiên trải nghiệm mua sắm. " + "chi tiết " * 220
        self.assertGreater(len(long_feedback), 360)
        with patch("agentforge.model.generate_json", return_value=revised_design()) as model:
            builder.propose(
                "nem-revision", BRIEF, source_proposal_id=original["proposal_id"],
                source_sha256=original["sha256"], revision_feedback=long_feedback)
            self.assertIn(long_feedback.strip(), model.call_args.args[0])
        self.assertEqual(len(list(builder.PROPOSALS.glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
