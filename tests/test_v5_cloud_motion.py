import unittest
from agentforge.features.film_studio import draft_motion_cloud as motion
from agentforge.features.film_studio import studio_runtime


class CloudMotionTests(unittest.TestCase):
    def test_registered_adapter_and_billed_duration(self):
        profile = {"provider": "ltx_cloud", "model": "ltx-2-3-fast"}
        self.assertIs(studio_runtime.motion_adapter(profile), motion)
        self.assertEqual(motion.output_profile().max_frames, 240)
        self.assertEqual([motion.billed_seconds(n) for n in (1,144,145,192,193,240)], [6,6,8,8,10,10])
        with self.assertRaises(ValueError):
            motion.billed_seconds(241)

    def test_no_budget_overrun(self):
        job = {"production_plan": {"method": "cloud", "max_cloud_seconds": 10},
               "approved_storyboard_sha": "sha", "cloud_motion_seconds": 6,
               "board": {"scenes": [{"frames": 144}]}}
        with self.assertRaises(ValueError):
            motion.prepare(job, None)
