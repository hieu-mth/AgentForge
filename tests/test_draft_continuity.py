import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge.features.film_studio import draft_continuity as continuity, motion_verify


class ContinuityTests(unittest.TestCase):
    def scenes(self):
        return [{"shot_id": str(i)*32, "description": "Cat", "frames": 24,
                 "motion_sha": str(i)*64, "motion_job": str(i)*32} for i in range(1, 5)]

    def test_ai_selects_boundaries_and_preserves_order(self):
        scenes = self.scenes()
        job = {"board": {"continuity": "Same cat", "scenes": scenes}}
        def infer(instructions, context, schema):
            return {"shots": [{"shot_id": scene["shot_id"], "transition": kind,
                               "start_state": "Cat stands", "end_state": "Cat sits"}
                              for scene, kind in zip(context["shots"], ("CUT", "CONTINUE", "CAMERA_CHANGE", "CUT"))]}
        plans = continuity.propose(job, infer)
        self.assertEqual(plans[1]["previous_shot_id"], scenes[0]["shot_id"])
        self.assertEqual(plans[1]["transition"], "CONTINUE")
        with self.assertRaisesRegex(ValueError, "order"):
            continuity.propose(job, lambda *args: {"shots": [
                {"shot_id": "wrong", "transition": "CUT", "start_state": "a", "end_state": "b"}]*4})

    def test_only_chained_descendants_invalidate(self):
        scenes = self.scenes()
        for index, scene in enumerate(scenes):
            scene["continuity_plan"] = {"transition": ("CUT", "CONTINUE", "CONTINUE", "CAMERA_CHANGE")[index],
                "start_state": "a", "end_state": "b",
                "previous_shot_id": scenes[index-1]["shot_id"] if index else None}
        old = [dict(scene) for scene in scenes]
        continuity.clear_motion(scenes[0])
        continuity.invalidate_dependencies(scenes, old, old)
        self.assertTrue(all("motion_sha" not in scene for scene in scenes[:3]))
        self.assertEqual(scenes[3]["motion_sha"], "4"*64)
        scenes.reverse()
        continuity.clear_stale_boundaries(scenes)
        self.assertNotIn("continuity_plan", scenes[0])

    def test_extracts_displayed_frame_from_real_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            clip = folder / "clip.mp4"
            ffmpeg = motion_verify.render._ffmpeg()
            motion_verify.render._run_process([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                "color=red:s=64x64:r=24:d=0.5", "-f", "lavfi", "-i",
                "color=blue:s=64x64:r=24:d=0.5", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
                "-c:v", "libx264", "-threads", "1",
                "-pix_fmt", "yuv420p", str(clip)], cwd=folder)
            sha = hashlib.sha256(clip.read_bytes()).hexdigest()
            source = {"motion_job": "a"*32, "motion_sha": sha, "frames": 12}
            receipt = {"clip_sha256": sha, "technical": {"frames_decoded": 24}, "film_slug": "d-"+"b"*32+"-v1"}
            with (patch.object(motion_verify, "inspect_receipt", return_value=receipt),
                  patch.object(motion_verify, "_job", return_value={}),
                  patch.object(motion_verify, "_dir", return_value=folder)):
                marker, png = motion_verify.read_continuation_frame(source, "d-"+"b"*32+"-v2")
                self.assertEqual(marker, "motion-frame:"+"a"*32+":11:"+sha)
                self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
                import io
                from PIL import Image
                with Image.open(io.BytesIO(png)) as frame:
                    red, green, blue = frame.convert("RGB").getpixel((16, 16))
                    self.assertGreater(red, 200)
                    self.assertLess(blue, 30)
                with self.assertRaises(ValueError):
                    motion_verify.read_continuation_frame(dict(source, frames=25), "d-"+"b"*32+"-v2")
                with self.assertRaises(ValueError):
                    motion_verify.read_continuation_frame(source, "d-"+"c"*32+"-v1")
