import unittest
from agentforge.features.film_studio import draft_motion_cloud as motion
from agentforge.features.film_studio import studio_runtime, studio_ltx_cloud


class CloudMotionTests(unittest.TestCase):
    def test_registered_adapter_and_billed_duration(self):
        profile = {"provider": "ltx_cloud", "model": "ltx-2-3-fast"}
        self.assertIs(studio_runtime.motion_adapter(profile), motion)
        self.assertEqual(motion.output_profile(profile).max_frames, 240)
        self.assertEqual([motion._profile_seconds(n, profile) for n in (1,144,145,192,193,240)], [6,6,8,8,10,10])
        with self.assertRaises(ValueError):
            motion._profile_seconds(241, profile)

    def test_no_budget_overrun(self):
        job = {"production_plan": {"method": "cloud", "max_cloud_seconds": 10},
               "approved_storyboard_sha": "sha", "cloud_motion_seconds": 6,
               "board": {"scenes": [{"frames": 144}]}}
        with self.assertRaises(ValueError):
            motion.prepare(job, None)


class CloudMotionIntegrationTests(unittest.TestCase):
    def test_cloud_direct_from_storyboard_to_verified_native_audio(self):
        import json
        import os
        import shutil
        import tempfile
        from contextlib import nullcontext
        from pathlib import Path
        from unittest.mock import patch

        from agentforge.ai import model_hub, orchestrator_policy
        from agentforge.features.film_studio import draft_pipeline as draft, studio_cloud
        from agentforge.features.media import render
        if not all(render.find_media_tool(tool) for tool in ("ffmpeg", "ffprobe")):
            self.skipTest("FFmpeg fixture requires installed media tools")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "fixture.mp4"
            render._run_process([render._ffmpeg(), "-nostdin", "-v", "error", "-f", "lavfi",
                "-i", "color=c=blue:s=1280x720:r=24:d=6", "-f", "lavfi",
                "-i", "sine=frequency=440:sample_rate=48000:duration=6",
                "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "6", str(fixture)], cwd=root, timeout=90)
            with (patch.object(model_hub, "DB_PATH", root/"hub.db"),
                  patch.object(draft, "DB", root/"draft.db"),
                  patch.object(draft, "WORKSPACE_DIR", root/"workspace"),
                  patch.object(motion, "DB", root/"cloud.db"),
                  patch.object(draft, "_dispatch"),
                  patch.object(draft, "_measured", side_effect=lambda *a, **k: nullcontext()),
                  patch.object(model_hub, "local_inference_slot", side_effect=lambda: nullcontext()),
                  patch.object(draft.ops_control, "require_active"),
                  patch.object(draft.characters, "list_characters", return_value={"characters": []}),
                  patch.object(draft, "_image", side_effect=AssertionError("FLUX generation invoked")),
                  patch.dict(os.environ, {"LTX_BASE_URL": "https://api.ltx.io", "LTX_API_KEY": "fixture-key"})):
                writer = {"id": "writer", "provider": "openai", "enabled": True,
                          "model": "fixture-writer", "base_url_env": "TEST_API_BASE", "api_key_env": "TEST_API_KEY"}
                video = {"id": "cloud_video", "provider": "ltx_cloud", "enabled": True,
                         "model": "ltx-2-3-fast", "base_url_env": "LTX_BASE_URL", "api_key_env": "LTX_API_KEY"}
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=writer)
                model_hub.change("SAVE_MODEL_PROFILE", expected_revision=1, profile=video)
                policy = orchestrator_policy.defaults()
                policy["permissions"].update(plan=True, assign_models=True, call_cloud=True, run_tools=True)
                policy["tools"] = ["ffmpeg"]
                model_hub.change("SET_MODEL_ROUTE", expected_revision=2, task_id="general.text", model_ref="writer")
                model_hub.change("SET_MODEL_ROUTE", expected_revision=3, task_id="film.storyboard", model_ref="writer")
                model_hub.change("SAVE_ORCHESTRATOR", expected_revision=4, policy=policy)
                job = draft.submit({"id": "a"*32, "idea": "Mèo nhìn cửa rồi bước đi.",
                                    "seconds": None, "scene_count": None, "ratio": "16:9",
                                    "mode": "motion", "duration_mode": "auto",
                                    "route_strategy": "cloud", "max_cloud_seconds": 12})
                plan = {"estimated_duration_seconds": 4, "production_feasibility": "feasible",
                        "duration_reasoning": "Hai hành động ngắn.", "shots": [
                            {"action": "Mèo nhìn cửa.", "reason": "Mở đầu", "suggested_seconds": 2},
                            {"action": "Mèo bước đi.", "reason": "Tiếp nối", "suggested_seconds": 2}]}
                shots = [{"title": "Mèo", "continuity": "Cùng căn phòng", "description": desc,
                          "image_prompt": prompt, "audio": "Quiet"}
                         for desc, prompt in (("Mèo nhìn cửa", "Cat looks at door"),
                                              ("Mèo bước đi", "Cat walks away"))]
                with patch.object(studio_cloud, "infer_structured", side_effect=[plan, *shots]):
                    draft._work(job, nullcontext())
                job = draft._read(job["id"])
                self.assertEqual(job["status"], "STORYBOARD_REVIEW", job.get("error"))
                self.assertEqual(job["production_plan"]["method"], "cloud")
                self.assertEqual(job["motion_plan"]["output"]["resolution"], [1280, 720])
                self.assertEqual(job["cloud_calls"], 3)
                self.assertNotIn("cloud_motion_seconds", job)
                draft._storyboard_action(job, "storyboard-approve", {"sha256": job["storyboard_sha"]})
                self.assertEqual(job["status"], "QUEUED")
                remote = iter(["d"*32, "e"*32])
                post_bodies = []

                def request(method, path, key, body=None):
                    if method == "POST":
                        post_bodies.append(body)
                        self.assertEqual(path, "/v2/text-to-video")
                        self.assertTrue(body["generate_audio"])
                        self.assertEqual(body["duration"], 6)
                        return {"id": next(remote)}
                    return {"id": path.rsplit("/", 1)[1], "status": "completed",
                            "result": {"video_url": "https://storage.googleapis.com/fixture/video.mp4"}}

                with (patch.object(studio_ltx_cloud, "_request", side_effect=request),
                      patch.object(studio_ltx_cloud, "_download", side_effect=lambda _, target: shutil.copyfile(fixture, target))):
                    draft._work(job, nullcontext())
                result = draft._read(job["id"])
                self.assertEqual(result["status"], "REVIEW", result.get("error"))
                self.assertEqual(len(post_bodies), 2)
                self.assertEqual(result["cloud_motion_seconds"], 12)
                self.assertEqual(result["cloud_calls"], 5)
                self.assertTrue(all(not s["asset"] and s["motion_sha"] for s in result["board"]["scenes"]))
                receipt = json.loads(draft.verified_receipt(result))
                self.assertEqual(receipt["technical"]["frames_decoded"], 96)
                self.assertTrue(receipt["audio"]["audio_decoded"])
                self.assertEqual(receipt["audio"]["mode"], "CLOUD_NATIVE")

    def test_ambiguous_post_is_not_repeated(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from agentforge.features.film_studio.draft_resources import NeedsReconciliation
        with tempfile.TemporaryDirectory() as tmp, patch.object(motion, "DB", Path(tmp)/"ledger.db"):
            job = {"production_plan": {"method": "cloud", "max_cloud_seconds": 6}}
            scene = {"frames": 144, "image_prompt": "Cat", "description": "Cat walks", "audio": "Quiet"}
            profile = {"model": "ltx-2-3-fast"}
            prepared = ("a"*32, job, Path(tmp), motion.workflow_sha())
            with (patch.object(motion, "_key", return_value="fixture"),
                  patch.object(motion, "_reserve"),
                  patch.object(motion.ops_control, "require_active"),
                  patch.object(studio_ltx_cloud, "_request", side_effect=ValueError("timeout")) as request):
                for _ in range(2):
                    with self.assertRaises(NeedsReconciliation):
                        motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(motion._row(scene["motion_job"])["state"], "SUBMITTING")

    def test_duplicate_remote_id_is_not_bound_or_resubmitted(self):
        import tempfile
        from pathlib import Path
        from contextlib import closing
        from unittest.mock import patch
        from agentforge.features.film_studio.draft_resources import NeedsReconciliation

        existing, remote = "a"*32, "b"*32
        with tempfile.TemporaryDirectory() as tmp, patch.object(motion, "DB", Path(tmp)/"ledger.db"):
            with closing(motion._db(True)) as conn, conn:
                conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                    (existing, "c"*32, "text-to-video", "ltx-2-3-fast", 6,
                     "d"*64, "SUBMITTED", remote, None))
            job = {"production_plan": {"method": "cloud", "max_cloud_seconds": 6}}
            scene = {"frames": 144, "image_prompt": "Cat", "description": "Cat walks", "audio": "Quiet"}
            profile = {"model": "ltx-2-3-fast"}
            prepared = ("e"*32, job, Path(tmp), motion.workflow_sha())
            with (patch.object(motion, "_key", return_value="fixture"),
                  patch.object(motion, "_reserve"),
                  patch.object(motion.ops_control, "require_active"),
                  patch.object(studio_ltx_cloud, "_request", return_value={"id": remote}) as request):
                for _ in range(2):
                    with self.assertRaises(NeedsReconciliation):
                        motion.run_shot(scene, 0, prepared, profile, lambda: None, lambda: False)
                request.assert_called_once()
                self.assertEqual(request.call_args.args[0], "POST")
            self.assertEqual(motion._row(existing)["provider_id"], remote)
            pending = motion._row(scene["motion_job"])
            self.assertEqual(pending["state"], "SUBMITTING")
            self.assertIsNone(pending["provider_id"])

    def test_recover_missing_provider_id_is_get_only_and_owner_attested(self):
        import tempfile
        from pathlib import Path
        from contextlib import closing
        from unittest.mock import patch
        ident, remote = "a"*32, "b"*32
        job = {"id": "c"*32, "status": "NEEDS_RECONCILIATION",
               "board": {"scenes": [{"motion_job": ident}]}}
        data = {"motion_job": ident, "provider_id": remote, "request_sha": "d"*64, "owner_matched": True}
        with tempfile.TemporaryDirectory() as tmp, patch.object(motion, "DB", Path(tmp)/"ledger.db"):
            with closing(motion._db(True)) as conn, conn:
                conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                    (ident, job["id"], "text-to-video", "ltx-2-3-fast", 6, data["request_sha"], "SUBMITTING", None, None))
            with (patch.object(motion.ops_control, "require_active"),
                  patch.object(motion, "_key", return_value="fixture"),
                  patch.object(studio_ltx_cloud, "_request", return_value={"id": remote, "status": "processing"}) as request):
                with self.assertRaises(PermissionError):
                    motion.recover_provider_id(job, {**data, "owner_matched": False}, {"model": "ltx-2-3-fast"})
                result = motion.recover_provider_id(job, data, {"model": "ltx-2-3-fast"})
                self.assertEqual(result["association"], "OWNER_ATTESTED")
                self.assertEqual(motion._row(ident)["state"], "SUBMITTED")
                self.assertEqual(motion._row(ident)["provider_id"], remote)
                self.assertEqual(request.call_args.args[0], "GET")
                with self.assertRaises(ValueError):
                    motion.recover_provider_id(job, data, {"model": "ltx-2-3-fast"})
                request.assert_called_once()

    def test_cancel_reconciliation_validates_all_shots_and_orphaned_jobs_before_polling(self):
        import tempfile
        from pathlib import Path
        from contextlib import closing
        from unittest.mock import patch
        from agentforge.features.film_studio import draft_pipeline as draft

        production, ident, other, remote = "a"*32, "b"*32, "c"*32, "d"*32
        profile = {"model": "ltx-2-3-fast"}
        job = {"id": production, "board": {"scenes": [{"motion_job": ident, "frames": 144}]}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(motion, "DB", Path(tmp)/"ledger.db"):
            with closing(motion._db(True)) as conn, conn:
                conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                    (ident, other, "text-to-video", profile["model"], 6, "e"*64, "SUBMITTED", remote, None))
            with (patch.object(draft, "_studio_bindings", return_value=(1, {"film.motion": profile}, 1)),
                  patch.object(motion, "_key", return_value="fixture"),
                  patch.object(studio_ltx_cloud, "_request", return_value={"id": remote, "status": "completed"}) as request):
                self.assertFalse(motion.reconcile_cancelled(job))
                request.assert_not_called()
                with closing(motion._db(True)) as conn, conn:
                    conn.execute("UPDATE jobs SET production=?, seconds=8 WHERE id=?", (production, ident))
                self.assertFalse(motion.reconcile_cancelled(job))
                request.assert_not_called()
                with closing(motion._db(True)) as conn, conn:
                    conn.execute("UPDATE jobs SET seconds=6 WHERE id=?", (ident,))
                    conn.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                        (other, production, "text-to-video", profile["model"], 6,
                         "f"*64, "SUBMITTING", None, None))
                self.assertFalse(motion.reconcile_cancelled(job))
                request.assert_not_called()
                with closing(motion._db(True)) as conn, conn:
                    conn.execute("DELETE FROM jobs WHERE id=?", (other,))
                self.assertTrue(motion.reconcile_cancelled(job))
                request.assert_called_once()
                self.assertEqual(request.call_args.args[0], "GET")
                self.assertEqual(motion._row(ident)["state"], "CANCELLED_REMOTE_TERMINAL")

    def test_cloud_poll_refuses_untrusted_endpoint_and_mismatched_metadata(self):
        from unittest.mock import patch
        from agentforge.features.film_studio.draft_resources import NeedsReconciliation

        remote = "a"*32
        row = {"endpoint": "../other", "provider_id": remote,
               "model": "ltx-2-3-fast", "seconds": 6}
        with (patch.object(motion, "_key", return_value="fixture"),
              patch.object(studio_ltx_cloud, "_request", return_value={
                  "id": remote, "status": "completed", "duration": 8}) as request):
            with self.assertRaises(NeedsReconciliation):
                motion._poll(row, {})
            request.assert_not_called()
            with self.assertRaises(NeedsReconciliation):
                motion._poll({**row, "endpoint": "text-to-video"}, {"provider": "ltx_cloud", "model": row["model"]})
            request.assert_called_once()

    def test_cloud_ledger_read_connection_cannot_write(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        from contextlib import closing
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp, patch.object(motion, "DB", Path(tmp)/"ledger.db"):
            self.assertIsNone(motion._db())
            self.assertFalse(motion.DB.exists())
            with closing(motion._db(True)):
                pass
            with closing(motion._db()) as conn:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("DELETE FROM jobs")
