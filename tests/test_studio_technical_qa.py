import io
import unittest
from unittest.mock import patch

from PIL import Image

from scripts import studio_technical_qa as qa


class StudioTechnicalQATests(unittest.TestCase):
    def test_valid_corrupt_and_missing_images_keep_creative_review_unverified(self):
        png = io.BytesIO()
        Image.new("RGB", (16, 16)).save(png, "PNG")
        job = {"id": "fixture", "brief": {}, "board": {"scenes": [
            {"asset": "present"}, {"asset": "present"}, {"asset": None}]}}
        with patch.object(qa.draft_pipeline, "image", side_effect=[png.getvalue(), b"broken"]) as read:
            result = qa.review(job)
        self.assertEqual([r["image"] for r in result["shots"]], ["PASS", "FAIL", "NOT_VERIFIED"])
        self.assertEqual(read.call_count, 2)
        self.assertEqual(result["final_mp4"], "NOT_VERIFIED")
        self.assertEqual(result["creative_quality"], "NOT_VERIFIED")
