"""UI-1A: existing byte caps, no implicit truncation/schema/model execution."""
import hashlib
import json
import tempfile
import unittest
import http.client
import threading
from pathlib import Path
from unittest.mock import patch

from agentforge import brain_planner, brain_store, task_history
from agentforge.ai.prompt_intake import plan_request
from agentforge.api.server import create_server


class PromptBudgetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "brain.db"
        self.tasks = Path(temp.name) / "tasks.db"
        for target, value in (
            ("agentforge.workspace_policy.read", {"website_enabled": True,
                "storyboard_enabled": True, "max_estimated_model_calls": 3}),
            ("agentforge.goal_preflight.require_ready", None),
        ):
            mock = patch(target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_unicode_and_v5_preserve_brief_sha_and_task_records(self):
        for prefix, suffix, calls in (
            ("Tạo website ", "Mô tả tiếng Việt có dấu. " * 35, 1),
            ("Create website ", "ASCII content " * 40, 1),
            ("Tạo website ", "🛏️😀 " * 80, 1),
            ("AI Company V5 ", "Ứng dụng bán hàng 😀 " * 40, 3),
        ):
            brief = (prefix + suffix).strip()
            with self.subTest(prefix=prefix, suffix=suffix[:12]), patch("agentforge.model.generate_json") as model:
                receipt = plan_request(brief, max_model_calls=calls, brain_db_path=self.db)
                model.assert_not_called()
            goal = brain_store.get_goal(receipt["goal_id"], db_path=self.db)
            self.assertEqual(goal["inputs"]["brief"], brief)
            raw = json.dumps(goal["plan"], ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
            self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), goal["plan_sha256"])
            for step in goal["plan"]:
                if "brief" in step["payload"]:
                    self.assertEqual(step["payload"]["brief"], brief)
                    ident = task_history.create_task("skill", step["skill_id"],
                        step["payload"], db_path=self.tasks)
                    self.assertEqual(task_history.get_task(ident, db_path=self.tasks)["request"]["brief"], brief)

    def test_reject_budget_before_any_database_write_and_no_truncation(self):
        for prompt, calls in (("Tạo website " + "ệ" * 5900, 1),
                              ("AI Company V5 " + "a" * 5900, 3),
                              ("Tạo website " + "😀" * 3000, 1)):
            with self.subTest(calls=calls), self.assertRaisesRegex(brain_store.BrainError, "PLAN_UTF8_BUDGET:.*8 KiB"):
                plan_request(prompt, max_model_calls=calls, brain_db_path=self.db)
            self.assertFalse(self.db.exists())
        self.assertEqual(brain_store.MAX_PLAN_BYTES, 8192)

    def test_exact_serialized_plan_boundary(self):
        # Measure the real signed plan, not a guessed character/word conversion.
        for template, char, calls in (("website.draft", "ệ", 1), ("webapp.company", "a", 3)):
            def fits(length):
                inputs = {"slug": "synthetic", "brief": "Tạo website " + char * length}
                plan = brain_planner.make_plan(template, inputs, max_model_calls=calls)
                return len(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode()) <= 8192
            low, high = 20, 5900
            while low < high:
                mid = (low + high + 1) // 2
                if fits(mid): low = mid
                else: high = mid - 1
            inputs = {"slug": "synthetic", "brief": "Tạo website " + char * low}
            receipt = brain_planner.propose("Synthetic boundary", template, inputs,
                max_model_calls=calls, db_path=self.db)
            before = len(brain_store.list_goals(db_path=self.db))
            with self.assertRaisesRegex(brain_store.BrainError, "PLAN_UTF8_BUDGET"):
                brain_planner.propose("Too large", template,
                    {**inputs, "brief": inputs["brief"] + char}, max_model_calls=calls, db_path=self.db)
            self.assertEqual(len(brain_store.list_goals(db_path=self.db)), before)
            self.assertEqual(brain_store.get_goal(receipt["goal_id"], db_path=self.db)["inputs"]["brief"], inputs["brief"])

    def test_character_boundaries_and_controls_remain_enforced(self):
        for value in ("short", "Tạo website " + "x" * 6000, "Tạo website nội dung\x00 không hợp lệ"):
            with self.assertRaises(ValueError):
                plan_request(value, brain_db_path=self.db)
        # 6000 characters is valid for a single-step ASCII website and fits storage.
        text = "Tạo website " + "a" * (6000 - len("Tạo website "))
        receipt = plan_request(text, brain_db_path=self.db)
        self.assertEqual(brain_store.get_goal(receipt["goal_id"], db_path=self.db)["inputs"]["brief"], text)


class PromptBudgetHttpTests(unittest.TestCase):
    def test_retired_owner_workspace_endpoint_fails_closed_without_model(self):
        from tests.owner_http_fixture import OwnerHttpFixture
        fixture = OwnerHttpFixture("test_noop")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.login()
        payload = {"ack": "PLAN_ONLY", "prompt": "Tạo website " + "ệ"*5900,
                   "max_model_calls": 1}
        with patch("agentforge.model.generate_json") as model:
            self.assertEqual(fixture.req("POST", "/api/workspace/request",
                                         payload, csrf=False)[0], 403)
            self.assertEqual(fixture.req("POST", "/api/workspace/request",
                                         payload)[0], 400)
            model.assert_not_called()
        self.assertFalse(fixture.brain.exists())
        self.assertFalse(fixture.tasks.exists())


if __name__ == "__main__":
    unittest.main()
