"""V1.4 Business Context, deterministic QA, immutable review, and V1.3 boundary tests."""
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agentforge import autopilot_v13 as ap
from agentforge import quality_v14 as qa

PROFILE = {
    "business": "Cửa hàng tư vấn nệm gia đình",
    "industry": "Nệm ngủ và phụ kiện phòng ngủ",
    "focus_phrases": ["nệm", "nệm ngủ", "giấc ngủ"],
    "blocked_phrases": ["nem chua", "nem nướng", "nem cua", "món ăn"],
}
GOOD = {
    "title": "Gợi ý chọn nệm ngủ",
    "scenes": [
        {"headline": "Nệm ngủ cho gia đình", "caption": "Chọn nệm theo nhu cầu thực tế.", "duration_seconds": 5},
        {"headline": "Tìm hiểu nệm", "caption": "Trao đổi về kích thước trước khi chọn.", "duration_seconds": 5}
    ],
    "status": "DRAFT_NOT_VERIFIED", "review_required": True, "verified_claims": False,
}
WRONG = {
    "title": "Storyboard Video: Tư Vấn Chọn Nem",
    "scenes": [
        {"headline": "Bạn đang tìm mua nem?",
         "caption": "Bạn phân vân giữa nhiều lựa chọn về nem chua và nem cua.",
         "duration_seconds": 5},
        {"headline": "Nem có nhiều loại",
         "caption": "Nem nướng đem lại hương vị khác nhau.", "duration_seconds": 6},
    ],
    "status": "DRAFT_NOT_VERIFIED", "review_required": True, "verified_claims": False,
}
VALID_INPUT = {
    "topic": "Tư vấn chọn nệm ngủ cho gia đình",
    "audience": "Khách hàng đang tìm mua nệm",
    "goal": "Tạo storyboard về nệm ngủ để owner duyệt",
}
AMBIGUOUS_INPUT = {
    "topic": "Tu van chon nem",
    "audience": "Nguoi mua nem",
    "goal": "Tao video ve nem",
}


class QualityV14Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "v14.sqlite3"

    def set_profile(self):
        return qa.set_profile(PROFILE, confirm=True, db_path=self.db)

    def setup_job(self, result=GOOD):
        self.set_profile()
        ap.configure(daily_cap=2, enabled=True, confirm=True, db_path=self.db)
        job = ap.submit("media.copy_draft", VALID_INPUT, db_path=self.db)
        with patch("agentforge.skill_runner.invoke", return_value={
            "status": "SUCCEEDED", "task_id": "a"*32, "result": result}):
            receipt = ap.tick(allow_model=True, db_path=self.db)
        return job, receipt

    def test_reproduces_real_world_wrong_nem_food(self):
        finding = qa.assess("media.copy_draft", WRONG, PROFILE)
        self.assertEqual("BLOCKED", finding["quality"])
        self.assertIn("BLOCKED_BUSINESS_TERMS", finding["reasons"])
        self.assertIn("NO_BUSINESS_FOCUS_EVIDENCE", finding["reasons"])

    def test_correct_nem_sleep_is_heuristic_only(self):
        finding = qa.assess("media.copy_draft", GOOD, PROFILE)
        self.assertEqual("PASS_HEURISTIC", finding["quality"])
        self.assertIn("HEURISTIC_ONLY_OWNER_REVIEW_REQUIRED", finding["reasons"])
        self.assertEqual("UNASSESSED", qa.assess("web.create", {
            "proposal_id":"a"*32}, PROFILE)["quality"])

    def test_context_requires_explicit_owner_and_bounded_fields(self):
        with self.assertRaises(PermissionError):
            qa.set_profile(PROFILE, db_path=self.db)
        bad = {**PROFILE, "secret": "not allowed"}
        with self.assertRaises(ValueError):
            qa.set_profile(bad, confirm=True, db_path=self.db)
        record = self.set_profile()
        self.assertEqual(64, len(record["profile_sha"]))
        self.assertEqual("Cửa hàng tư vấn nệm gia đình",
                         qa.inbox(db_path=self.db)["business_context"]["business"])

    def test_ambiguous_brief_rejected_before_queue_or_quota(self):
        self.set_profile()
        ap.configure(daily_cap=1, enabled=True, confirm=True, db_path=self.db)
        with self.assertRaises(ValueError):
            ap.submit("media.copy_draft", AMBIGUOUS_INPUT, db_path=self.db)
        self.assertEqual([], ap.report(db_path=self.db)["jobs"])
        self.assertEqual(0, ap.report(db_path=self.db)["used_today"])

    def test_successful_model_execution_is_still_pending_review(self):
        job, receipt = self.setup_job()
        self.assertEqual("SUCCEEDED", receipt["status"])
        self.assertEqual("PASS_HEURISTIC", receipt["quality"]["quality"])
        reviews = qa.inbox(db_path=self.db)["reviews"]
        self.assertEqual(1, len(reviews))
        self.assertEqual("PENDING", reviews[0]["decision"])
        self.assertEqual(job["job_id"], reviews[0]["job_id"])
        self.assertEqual(64, len(reviews[0]["output_sha"]))
        self.assertNotIn("Tìm hiểu nệm", json.dumps(reviews))
        self.assertNotIn("caption", json.dumps(reviews))

    def test_wrong_model_result_never_auto_passes_and_cannot_approve(self):
        job, receipt = self.setup_job(WRONG)
        self.assertEqual("SUCCEEDED", receipt["status"])  # technical status only
        self.assertEqual("BLOCKED", receipt["quality"]["quality"])
        inbox = qa.inbox(db_path=self.db)["reviews"][0]
        with self.assertRaises(PermissionError):
            qa.decide(job["job_id"], "APPROVE", inbox["output_sha"],
                      confirm=True, db_path=self.db)
        self.assertEqual("PENDING", qa.inbox(db_path=self.db)["reviews"][0]["decision"])
        rejected = qa.decide(job["job_id"], "REJECT", inbox["output_sha"],
                             confirm=True, db_path=self.db)
        self.assertEqual("REJECTED", rejected["decision"])
        self.assertFalse(rejected["published"])

    def test_sha_bound_one_time_owner_review_and_no_side_effects(self):
        job, _ = self.setup_job()
        row = qa.inbox(db_path=self.db)["reviews"][0]
        with self.assertRaises(PermissionError):
            qa.decide(job["job_id"], "APPROVE", row["output_sha"], db_path=self.db)
        with self.assertRaises(PermissionError):
            qa.decide(job["job_id"], "APPROVE", "f"*64,
                      confirm=True, db_path=self.db)
        result = qa.decide(job["job_id"], "APPROVE", row["output_sha"],
                           confirm=True, db_path=self.db)
        self.assertEqual("APPROVED", result["decision"])
        self.assertFalse(result["applied"])
        self.assertFalse(result["auto_next_step"])
        with self.assertRaises(PermissionError):
            qa.decide(job["job_id"], "REJECT", row["output_sha"],
                      confirm=True, db_path=self.db)

    def test_profile_change_does_not_silently_reassign_queued_job(self):
        self.set_profile()
        ap.configure(daily_cap=1, enabled=True, confirm=True, db_path=self.db)
        job = ap.submit("media.copy_draft", VALID_INPUT, db_path=self.db)
        changed = {**PROFILE, "focus_phrases": ["gối ngủ"]}
        qa.set_profile(changed, confirm=True, db_path=self.db)
        self.assertEqual("INPUT_REVIEW_REQUIRED",
                         ap._claim(db_path=self.db)["status"])
        self.assertEqual(0, ap.report(db_path=self.db)["used_today"])
        self.assertEqual("BLOCKED_INPUT", ap.report(db_path=self.db)["jobs"][0]["status"])

    def test_unreviewed_legacy_jobs_do_not_inherit_new_business_context(self):
        ap.configure(daily_cap=1, enabled=True, confirm=True, db_path=self.db)
        ap.submit("media.copy_draft", AMBIGUOUS_INPUT, db_path=self.db)
        self.set_profile()
        self.assertEqual("INPUT_REVIEW_REQUIRED",
                         ap._claim(db_path=self.db)["status"])
        self.assertEqual(0, ap.report(db_path=self.db)["used_today"])

    def test_website_proposal_stays_unassessed_without_source_access(self):
        self.set_profile()
        ap.configure(daily_cap=1, enabled=True, confirm=True, db_path=self.db)
        job = ap.submit("web.create", {
            "slug":"nem-ngu-v14",
            "brief":"Thiết kế website tư vấn chọn nệm ngủ cho gia đình."}, db_path=self.db)
        with patch("agentforge.skill_runner.invoke", return_value={
            "status":"SUCCEEDED", "task_id":"b"*32, "result":{
                "proposal_id":"c"*32,"sha256":"d"*64, "project_slug":"nem-ngu-v14"}}):
            receipt = ap.tick(allow_model=True, db_path=self.db)
        self.assertEqual("UNASSESSED", receipt["quality"]["quality"])
        row = qa.inbox(db_path=self.db)["reviews"][0]
        self.assertEqual(job["job_id"], row["job_id"])
        with self.assertRaises(PermissionError):
            qa.decide(job["job_id"], "APPROVE", row["output_sha"],
                      confirm=True, db_path=self.db)

    def test_recurring_brief_mismatch_blocks_owner_schedule(self):
        self.set_profile()
        due = datetime.now(timezone.utc)+timedelta(hours=1)
        with self.assertRaises(ValueError):
            ap.schedule("media.copy_draft", AMBIGUOUS_INPUT, due.isoformat(),
                        1440, confirm=True, db_path=self.db)
        self.assertEqual([], ap.report(db_path=self.db)["schedules"])

    def test_schedule_pause_requires_confirmation(self):
        due = datetime.now(timezone.utc)+timedelta(hours=1)
        sched = ap.schedule("media.copy_draft", AMBIGUOUS_INPUT,
                            due.isoformat(), 1440, confirm=True, db_path=self.db)
        with self.assertRaises(PermissionError):
            qa.pause_schedule(sched["schedule_id"], db_path=self.db)
        paused = qa.pause_schedule(sched["schedule_id"], confirm=True,
                                   db_path=self.db)
        self.assertEqual("PAUSED", paused["status"])
        self.assertEqual(0, ap.report(db_path=self.db)["schedules"][0]["enabled"])


    def test_existing_v13_db_migrates_on_inbox_read(self):
        # V1.3 local production has tables but no V1.4 migration yet.
        ap.configure(daily_cap=1, enabled=False, confirm=True, db_path=self.db)
        from contextlib import closing
        with closing(sqlite3.connect(self.db)) as conn:
            with conn:
                conn.execute("DROP TABLE IF EXISTS content_reviews")
                conn.execute("DROP TABLE IF EXISTS job_context")
                conn.execute("DROP TABLE IF EXISTS business_profile")
        review = qa.inbox(db_path=self.db)
        self.assertEqual([], review["reviews"])
        self.assertIsNone(review["business_context"])
        self.assertEqual(1, ap.policy(db_path=self.db)["daily_cap"])

    def test_existing_bad_recurring_schedule_pauses_without_model_call(self):
        due = datetime.now(timezone.utc) + timedelta(hours=1)
        scheduled = ap.schedule("media.copy_draft", AMBIGUOUS_INPUT,
                                due.isoformat(), 1440, confirm=True, db_path=self.db)
        self.set_profile()
        ap.configure(daily_cap=1, enabled=True, confirm=True, db_path=self.db)
        outcome = ap.enqueue_due(db_path=self.db, now=due+timedelta(minutes=1))
        self.assertEqual("SCHEDULE_PAUSED_INPUT_REVIEW", outcome["status"])
        self.assertEqual(scheduled["schedule_id"], outcome["schedule_id"])
        self.assertEqual(0, ap.report(db_path=self.db)["used_today"])
        self.assertEqual([], ap.report(db_path=self.db)["jobs"])
        self.assertEqual(0, ap.report(db_path=self.db)["schedules"][0]["enabled"])

if __name__ == "__main__":
    unittest.main()
