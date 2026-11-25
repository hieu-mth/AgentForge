import unittest
from unittest.mock import patch
from agentforge.features.film_studio import draft_quality as quality


class QualityBatchTests(unittest.TestCase):
    def job(self):
        scenes = [{"shot_id": str(i), "asset": "a", "motion_sha": "m"} for i in range(3)]
        return {"status": "REVIEW", "video_sha": "v", "storyboard_sha": "s",
                "approved_storyboard_sha": "s", "board": {"scenes": scenes},
                "visual_reviews": {"0": {"shot_id": "0", "video_sha": "v", "storyboard_sha": "s",
                                       "asset_sha": "a", "motion_sha": "m", "verdict": "FAIL"}}}

    @patch.object(quality.draft_timeline, "digest", return_value="s")
    def test_batch_skips_current_and_is_bounded(self, _):
        job = self.job()
        with patch.object(quality, "review", return_value=job) as review:
            quality.review_batch(job, {"sha256": "s", "video_sha": "v", "allow_cloud": False, "max_reviews": 1})
            self.assertEqual(review.call_count, 1)
            self.assertEqual(review.call_args.args[1]["index"], 1)
        with self.assertRaises(ValueError):
            quality.review_batch(job, {"sha256": "s", "video_sha": "old", "allow_cloud": False, "max_reviews": 1})

    @patch.object(quality.draft_timeline, "digest", return_value="s")
    def test_only_failed_current_shots_and_lifetime_cap(self, _):
        job = self.job()
        data = {"sha256": "s", "video_sha": "v", "max_repairs": 2}
        self.assertEqual([i for i, _ in quality.repair_targets(job, data)], [0])
        job["qa_repairs"] = 2
        with self.assertRaises(ValueError):
            quality.repair_targets(job, data)
        job["qa_repairs"] = 0
        job["visual_reviews"]["0"]["motion_sha"] = "old"
        with self.assertRaises(ValueError):
            quality.repair_targets(job, data)
