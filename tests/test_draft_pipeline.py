"""Draft schema, checkpoint lifecycle, and real local MP4 quality gate."""
import tempfile
import io
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack, closing, nullcontext
from types import SimpleNamespace
from uuid import uuid4

from agentforge.features.film_studio import draft_motion, draft_pipeline as draft, studio_ollama, studio_runtime
from agentforge.features.media import flux_runtime, studio_flux
from tests import owner_http_fixture
from tests.test_flux_runtime import profile as flux_profile


class DraftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in (("DB", self.root / "drafts.sqlite3"), ("WORKSPACE_DIR", self.root)):
            override = patch.object(draft, name, value)
            override.start()
            self.addCleanup(override.stop)
        self.enterContext(patch.object(draft.model_hub, "DB_PATH", self.root / "hub.sqlite3"))
        self.ident = "a" * 32
        self.brief = {"idea": "Chú mèo cam", "scene_count": 2, "ratio": "16:9", "seconds": 6}
        self.capacity = {"ram_available": 16 << 30, "commit_used": 8 << 30,
                         "commit_limit": 32 << 30, "vram_free_mib": 8000}
        capacity = patch.object(draft.draft_resources, "snapshot", return_value=self.capacity)
        capacity.start()
        self.addCleanup(capacity.stop)

    def board(self):
        scene = {"description": "Mèo ngắm rừng", "image_prompt": "Cat in a forest",
                 "character_ids": ["cat"], "audio": "Im lặng"}
        return {"title": "Mèo", "continuity": "Orange cat, morning", "scenes": [scene, scene]}

    def motion_profile(self):
        return {"id": "owner_motion", "provider": "comfyui", "model": draft_motion.motion_ltx.CHECKPOINT,
                "motion_encoder": str(self.root / "encoder.safetensors"), "base_url": "http://127.0.0.1:8188"}

    def registry_change(self, action, **kwargs):
        return draft.model_hub.change(action, expected_revision=draft.model_hub.catalog()["revision"], **kwargs)

    def assert_registry_writer_blocked(self):
        with closing(sqlite3.connect(draft.model_hub.DB_PATH, timeout=0)) as conn:
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                conn.execute("BEGIN IMMEDIATE")

    def seed_registry(self, image, motion):
        text = {"id": "owner_planner", "provider": "ollama", "enabled": True,
                "model": "planner:8b", "base_url": "http://127.0.0.1:11434"}
        writer = {**text, "id": "owner_story", "model": "writer:8b"}
        for profile in (text, writer, image, motion):
            self.registry_change("SAVE_MODEL_PROFILE", profile=profile)
        policy = draft.model_hub.orchestrator_policy.defaults()
        policy.update(permissions=dict.fromkeys(policy["permissions"], True), tools=["ffmpeg"])
        return self.registry_change("SAVE_ORCHESTRATOR", policy=policy, route_changes={
            "general.text": text["id"], "film.storyboard": writer["id"],
            "image.generate": image["id"], "film.motion": motion["id"]})["revision"]

    def test_legacy_approval_uses_historical_bindings_without_changing_digest(self):
        original = {**self.motion_profile(), "enabled": True}
        revision = self.seed_registry(flux_profile(), original)
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion", "seconds": 4},
               "motion_revision": revision, "storyboard_version": 1,
               "board": draft._story(self.board(), 2, 4, {"cat": {}}), "video_sha": None}
        draft._stamp_storyboard(job)
        job["approved_storyboard_sha"] = job["storyboard_sha"]
        draft._save(job)
        self.registry_change("SAVE_MODEL_PROFILE", profile={
            "id": "cloud_config", "provider": "anthropic", "model": "unused", "enabled": True,
            **draft.model_hub.ADAPTERS["anthropic"]["legacy_defaults"]})
        saved = draft._read(self.ident)
        current, _, legacy = draft._studio_bindings(saved)
        self.assertGreater(current, revision)
        self.assertEqual(legacy, revision)
        self.assertEqual(draft.draft_timeline.digest(saved), saved["approved_storyboard_sha"])
        self.assertNotIn("studio_plan", saved)
        self.registry_change("SET_MODEL_ROUTE", task_id="general.text", model_ref="cloud_config")
        with self.assertRaisesRegex(ValueError, "Studio chỉ chạy model local"):
            draft._studio_bindings(saved)
        self.registry_change("RESET_MODEL_ROUTE", task_id="general.text")
        self.registry_change("DELETE_MODEL_PROFILE", profile_id="owner_planner")
        with self.assertRaisesRegex(ValueError, "chưa phân công"):
            draft._studio_bindings(saved)
        self.registry_change("ROLLBACK_MODEL_HUB", target_revision=revision)
        self.assertEqual(draft._studio_bindings(saved)[2], revision)

    def test_flux_dispatch_checks_approved_profile_again_before_gpu_admission(self):
        image = flux_profile()
        old_revision = self.seed_registry(image, {**self.motion_profile(), "enabled": True})
        replacement = {**image, "id": "different_owner_flux"}
        self.registry_change("SAVE_MODEL_PROFILE", profile=replacement)
        with (patch.object(flux_runtime, "WORKSPACE_DIR", self.root),
              patch.object(draft.model_hub, "image_runtime", side_effect=AssertionError("re-resolved image route")),
              patch.object(draft.draft_resources, "require_gpu",
                           side_effect=draft.draft_resources.ResourceBlocked("TEST_GPU_GATE")) as gate):
            with self.assertRaisesRegex(draft.draft_resources.ResourceBlocked, "TEST_GPU_GATE"):
                flux_runtime.generate("A cat", production_profile=image, production_revision=old_revision)
            self.registry_change("SET_MODEL_ROUTE", task_id="image.generate", model_ref=replacement["id"])
            with self.assertRaisesRegex(draft.model_hub.ModelConfigError, "workflow tạo ảnh đã đổi"):
                flux_runtime.generate("A cat", production_profile=image, production_revision=old_revision)
            gate.assert_called_once_with("image")

    def test_casting_uses_pinned_storyboard_unless_owner_assigns_local_cast_route(self):
        self.seed_registry(flux_profile(), {**self.motion_profile(), "enabled": True})
        _, bindings = draft.model_hub.draft_routes()
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion"},
               "studio_plan": studio_runtime.routing_identity(bindings, moving=True)}
        with (patch.object(draft.characters, "list_characters", return_value={
                  "characters": [{"id": "cat", "name": "Miu", "appearance": "Orange cat"}]}),
              patch.object(draft, "_activity"), patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", return_value={"ids": ["cat"]}) as ask):
            self.assertIn("cat", draft._select_cast(job, bindings, "A cat"))
            self.assertEqual(ask.call_args.args[0]["id"], "owner_story")
            policy = draft.model_hub.orchestrator_policy.defaults()
            policy.update(permissions=dict.fromkeys(policy["permissions"], True), tools=["ffmpeg"],
                          mappings={"character.select": "owner_planner"})
            self.registry_change("SAVE_ORCHESTRATOR", policy=policy, route_changes={})
            with self.assertRaisesRegex(ValueError, "character.select"):
                draft._studio_bindings(job)
            _, explicit = draft.model_hub.draft_routes()
            self.assertIn("cat", draft._select_cast(job, explicit, "A cat"))
            self.assertEqual(ask.call_args.args[0]["id"], "owner_planner")

    def test_flux_reroute_during_readiness_cannot_submit_and_post_serializes_writers(self):
        image = flux_profile()
        self.seed_registry(image, {**self.motion_profile(), "enabled": True})
        _, bindings = draft.model_hub.draft_routes(moving=False)
        job = {"id": self.ident, "brief": self.brief,
               "studio_plan": studio_runtime.routing_identity(bindings, moving=False)}
        alternative = {**image, "id": "other_image"}
        self.registry_change("SAVE_MODEL_PROFILE", profile=alternative)
        db = self.root / "visual.sqlite3"

        def reroute(*args):
            self.registry_change("SET_MODEL_ROUTE", task_id="image.generate", model_ref=alternative["id"])
            return "READY"

        def provider(path, **kwargs):
            if path == "/queue":
                return {"queue_running": [], "queue_pending": []}
            self.assertEqual(path, "/prompt")
            self.assert_registry_writer_blocked()
            return {"prompt_id": str(uuid4())}

        def collect(*args, **kwargs):
            # Collection must not hold the registry lock.
            self.registry_change("SAVE_MODEL_PROFILE", profile=alternative)
            raise flux_runtime.JobError("OUTPUT_MISSING")

        def generate():
            return flux_runtime.generate("A cat", production_profile=image, db_path=db,
                                         dispatch_guard=lambda: draft._dispatch_guard(job))

        with (patch.object(flux_runtime, "WORKSPACE_DIR", self.root),
              patch.object(flux_runtime, "readiness", side_effect=reroute) as readiness,
              patch.object(draft.draft_resources, "require_gpu"),
              patch.object(draft.comfy_service, "require_other_queue_idle"),
              patch.object(flux_runtime, "_json", side_effect=provider) as transport,
              patch.object(flux_runtime, "_collect", side_effect=collect)):
            with self.assertRaisesRegex(ValueError, "image.generate"):
                generate()
            self.assertFalse(db.exists())
            transport.assert_not_called()
            self.registry_change("SET_MODEL_ROUTE", task_id="image.generate", model_ref=image["id"])
            readiness.side_effect = None
            readiness.return_value = "READY"
            self.assertEqual(generate()["status"], "OUTPUT_MISSING")
            self.assertEqual([call.args[0] for call in transport.call_args_list], ["/queue", "/prompt"])

    def test_legacy_motion_edit_pins_original_runtime_and_reapproval_resumes(self):
        profile = self.motion_profile()
        bindings = {"film.motion": profile, "image.generate": {}}
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion", "seconds": 4},
               "board": draft._story(self.board(), 2, 4, {"cat": {}}),
               "storyboard_version": 1, "status": "FAILED",
               "motion_revision": 8, "video_sha": None}
        draft._stamp_storyboard(job)
        job.update(status="FAILED", approved_storyboard_sha=job["storyboard_sha"])
        draft._save(job)
        old_sha = job["storyboard_sha"]
        folder = draft._folder(self.ident)
        folder.mkdir(parents=True)
        workflow = folder / "motion-workflow.json"
        workflow.write_bytes(draft_motion._workflow_bytes())
        fields = {"sha256": old_sha, "index": 0, "description": "Cat moves",
                  "image_prompt": "Cat by the window", "motion_prompt": "Cat pauses"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, bindings)) as routes,
              patch.object(draft_motion, "require_resolved_ledger"),
              patch.object(draft_motion, "bind", return_value=profile),
              patch.object(draft_motion, "prepare",
                           return_value=(None, None, None, draft_motion.workflow_sha())),
              patch.object(draft_motion, "run_shot") as motion,
              patch.object(draft, "_image"), patch.object(draft, "_release_idle_image"),
              patch.object(draft, "_dispatch"), patch.object(draft, "_render", return_value="sha")):
            self.assertNotIn("motion_plan", draft._read(self.ident))
            draft._work(draft._read(self.ident), nullcontext())
            saved = draft._read(self.ident)
            self.assertEqual(saved["status"], "REVIEW", saved.get("error"))
            self.assertEqual(motion.call_count, 2)
            routes.return_value = (9, bindings)
            with self.assertRaisesRegex(ValueError, "model gốc"):
                draft.act(self.ident, "storyboard-edit", fields)
            routes.return_value = (8, bindings)
            workflow.write_text(json.dumps(draft_motion.motion_ltx.workflow(33)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Stored motion workflow differs"):
                draft.act(self.ident, "storyboard-edit", fields)
            workflow.write_bytes(draft_motion._workflow_bytes())
            edited = draft.act(self.ident, "storyboard-edit", fields)
            self.assertEqual(edited["storyboard_history"][0]["sha256"], old_sha)
            self.assertNotIn("approved_motion", edited)
            self.assertEqual(edited["storyboard_sha"], draft.draft_timeline.digest(edited))
            sha = {"sha256": edited["storyboard_sha"]}
            for changed in ({**profile, "motion_encoder": str(self.root / "other.safetensors")},
                            {**profile, "model": draft_motion.motion_ltx.MODEL_ID}):
                routes.return_value = (8, {**bindings, "film.motion": changed})
                with self.assertRaisesRegex(ValueError, "new production"):
                    draft.act(self.ident, "storyboard-approve", sha)
            routes.return_value = (8, bindings)
            with patch.object(draft_motion, "workflow_sha", return_value="f" * 64):
                with self.assertRaisesRegex(ValueError, "workflow changed"):
                    draft.act(self.ident, "storyboard-approve", sha)
            approved = draft.act(self.ident, "storyboard-approve", sha)
            self.assertEqual(approved["approved_motion"], approved["motion_plan"])
            self.assertEqual(draft.draft_timeline.digest(approved), sha["sha256"])
            routes.return_value = (8, {**bindings, "film.motion": {
                **profile, "motion_encoder": str(self.root / "other.safetensors")}})
            draft._work(draft._read(self.ident), nullcontext())
            self.assertIn("encoder or workflow changed", draft._read(self.ident)["error"])
            self.assertEqual(motion.call_count, 2)
            routes.return_value = (8, bindings)
            draft._work(draft._read(self.ident), nullcontext())
            self.assertEqual(draft._read(self.ident)["status"], "REVIEW")
            self.assertEqual(motion.call_count, 4)

    def test_alternate_motion_contract_survives_approval_resume_and_render(self):
        class AlternateMotion:
            ADAPTER_ID = "fixture.video.v1"
            digest = "a" * 64

            def supports(self, profile):
                return profile.get("provider") == "comfyui" and profile.get("model") == "fixture-motion"

            def workflow_sha(self):
                return self.digest

            def weights_identity(self):
                return {"fixture-motion": "b" * 64}

            def output_profile(self):
                return studio_runtime.MotionOutput(12, 36, (320, 192))

            def bind(self, profile):
                return profile

            def clip_path(self, scene):
                return clip

        adapter = AlternateMotion()
        profile = {"id": "alternate", "provider": "comfyui", "model": "fixture-motion"}
        bindings = {"film.motion": profile}
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion", "duration_mode": "manual"},
               "board": self.board(), "storyboard_version": 1, "status": "RUNNING", "video_sha": None}
        with (patch.object(studio_runtime, "MOTION_ADAPTERS", (draft_motion, adapter)),
              patch.object(draft.model_hub, "draft_routes", return_value=(8, bindings))):
            self.assertIs(studio_runtime.motion_adapter(profile), adapter)
            with self.assertRaises(ValueError):
                studio_runtime.motion_adapter({**profile, "model": "unsupported"})
            self.assertEqual(studio_runtime.job_output(job), studio_runtime.MotionOutput(24, 49, (512, 288)))
            board = job.pop("board")
            board["scenes"] = [dict(scene) for scene in board["scenes"]]
            with self.assertRaisesRegex(ValueError, "original motion runtime"):
                draft._resolve_job_motion({**job, "board": board}, profile)
            draft._resolve_job_motion(job, profile, planning=True)
            job["board"] = board
            draft._stamp_storyboard(job)
            self.assertEqual([scene["frames"] for scene in board["scenes"]], [36, 36])
            draft._save(job)
            draft.act(self.ident, "storyboard-approve", {"sha256": job["storyboard_sha"]})
            reloaded = draft._read(self.ident)
            self.assertEqual(reloaded["motion_plan"], reloaded["approved_motion"])
            self.assertIs(studio_runtime.motion_artifacts(reloaded), adapter)
            self.assertIs(draft._resolve_job_motion(reloaded, profile)[0], adapter)

            adapter.digest = "c" * 64
            with patch.object(draft, "_dispatch"), patch.object(draft, "_image") as submit_image:
                draft._work(reloaded, nullcontext())
            self.assertIn("workflow changed", draft._read(self.ident)["error"])
            submit_image.assert_not_called()
            adapter.digest = "a" * 64

            folder = draft._folder(self.ident)
            folder.mkdir(parents=True)
            clip = folder / "source.mp4"
            ffmpeg = draft.render._ffmpeg()
            draft.render._run_process([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=320x192:rate=12", "-frames:v", "36", "-c:v", "libx264", str(clip)], cwd=folder)
            reloaded["video_sha"] = draft._render(reloaded)
            self.assertEqual(json.loads(draft.verified_receipt(reloaded))["technical"],
                             {"frames_decoded": 72, "fps": 12, "width": 320, "height": 192})

    def test_runtime_selection_uses_registry_provider_and_refuses_cloud(self):
        transport = studio_ollama.runtime
        with (patch.object(transport, "_installed_local_model", return_value=True),
              patch.object(transport, "_http_json", return_value={
                  "done": True, "message": {"content": '{"ready": true}'}}) as call):
            for name in ("planner-alpha:8b", "planner-beta:4b"):
                profile = {"id": "owner_planner", "provider": "ollama", "model": name,
                           "base_url": "http://127.0.0.1:11434"}
                self.assertEqual(draft._ask(profile, "Plan", {}, {}, None), {"ready": True})
                self.assertEqual(call.call_args.kwargs["payload"]["model"], name)
            with self.assertRaisesRegex(ValueError, "supported local text"):
                draft._ask({"provider": "anthropic"}, "Plan", {}, {}, None)
            self.assertEqual(call.call_count, 2)
        self.assertIs(studio_runtime.image_adapter(flux_profile()), studio_flux)
        self.assertIs(studio_runtime.motion_adapter(self.motion_profile()), draft_motion)
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            draft_motion.bind({"provider": "comfyui", "model": "wrong.safetensors",
                               "base_url": "http://127.0.0.1:8188"})
        for resolve in (studio_runtime.image_adapter, studio_runtime.motion_adapter):
            with self.assertRaises(ValueError):
                resolve({"provider": "ollama"})

    def test_resume_refuses_a_revision_change_before_any_model_calls(self):
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion"},
               "status": "RUNNING", "stage": "IMAGES", "motion_revision": 8,
               "board": self.board(), "storyboard_version": 1}
        job["approved_storyboard_sha"] = draft.draft_timeline.digest(job)
        with (patch.object(draft.model_hub, "draft_routes", return_value=(9, {})),
              patch.object(draft, "_dispatch"),
              patch.object(studio_runtime, "image_adapter") as image,
              patch.object(studio_runtime, "motion_adapter") as motion):
            draft._work(job, nullcontext())
        self.assertEqual(draft._read(self.ident)["status"], "FAILED")
        self.assertIn("model gốc", draft._read(self.ident)["error"])
        image.assert_not_called()
        motion.assert_not_called()

    def test_media_tools_resolve_from_agentforge_directory_without_path(self):
        tools = self.root / "runtime_tools" / "ffmpeg"
        tools.mkdir(parents=True)
        suffix = ".exe" if draft.render.os.name == "nt" else ""
        ffmpeg = tools / ("ffmpeg" + suffix)
        ffmpeg.touch()
        with (patch.object(draft.render, "COMPANY_DATA_DIR", self.root),
              patch.object(draft.render.shutil, "which", return_value=None)):
            self.assertEqual(draft.render._ffmpeg(), str(ffmpeg))
            self.assertIsNone(draft.render.find_media_tool("ffprobe"))
            ffprobe = tools / ("ffprobe" + suffix)
            ffprobe.touch()
            self.assertEqual(draft.render.find_media_tool("ffprobe"), str(ffprobe))
            with self.assertRaises(ValueError):
                draft.render.find_media_tool("python")

    def test_finished_drafts_are_read_only_for_scene_edits(self):
        for status in ("APPROVED", "REJECTED", "CANCELLED"):
            with self.subTest(status=status):
                job = {"id": self.ident, "brief": self.brief, "board": self.board(), "status": status}
                draft._save(job)
                with self.assertRaisesRegex(ValueError, "Scene cannot be edited"):
                    draft.act(self.ident, "edit", {})
                job["storyboard_version"] = 1
                job["storyboard_sha"] = draft.draft_timeline.digest(job)
                draft._save(job)
                with self.assertRaisesRegex(ValueError, "Storyboard chưa thể chỉnh"):
                    draft.act(self.ident, "storyboard-edit", {"sha256": job["storyboard_sha"]})
                self.assertEqual(draft._read(self.ident)["status"], status)

    def test_delete_cleans_only_inactive_unfinished_draft(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING"}
        folder = draft._folder(self.ident)
        folder.mkdir(parents=True)
        (folder / "scene.png").write_bytes(b"draft")
        other = folder.parent.with_name("b" * 32)
        other.mkdir()
        motion = draft_motion.motion_comfy
        ledger = self.root / "motion.sqlite3"
        with patch.object(motion, "DB", ledger):
            draft._save(job)
            with self.assertRaises(ValueError):
                draft.act(self.ident, "delete", {})
            with patch.object(draft, "_dispatch"):
                draft.act(self.ident, "cancel", {})
            self.assertTrue(draft._cancellation(self.ident))
            conn = sqlite3.connect(ledger)
            try:
                with conn:
                    conn.execute("CREATE TABLE motion_jobs (film_slug TEXT, state TEXT)")
                    conn.execute("INSERT INTO motion_jobs VALUES (?, 'SUBMITTED')", (f"d-{self.ident}-v2",))
                with self.assertRaises(ValueError):
                    draft.act(self.ident, "delete", {})
                self.assertTrue(folder.is_dir())
                with conn:
                    conn.execute("UPDATE motion_jobs SET state='FAILED'")
                job = draft._read(self.ident)
                job["storyboard_history"] = [{"video_sha": "previous render"}]
                draft._save(job)
                with self.assertRaises(ValueError):
                    draft.act(self.ident, "delete", {})
                job.pop("storyboard_history")
                draft._save(job)
                self.assertEqual(draft.act(self.ident, "delete", {}), {"id": self.ident, "deleted": True})
                self.assertFalse(folder.parent.exists())
                self.assertTrue(other.is_dir())
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM motion_jobs").fetchone()[0], 1)
                self.assertFalse(draft._cancellation(self.ident))
                with self.assertRaises(draft.DraftNotFound):
                    draft._read(self.ident)
            finally:
                conn.close()

    def test_ai_duration_cpu_planning_and_exact_frame_budget(self):
        for estimate, count in ((4, 2), (6, 3), (15, 8), (17, 9), (30, 15), (48, 25), (60, 30)):
            with self.subTest(estimate=estimate):
                proposed = {"estimated_duration_seconds": estimate, "recommended_shot_count": 1,
                            "shots": [{"action": "Miu tìm bạn", "reason": "Mở đầu",
                                       "suggested_seconds": estimate / count}] * count,
                            "duration_reasoning": "Dành thời gian cho các hành động chính.",
                            "production_feasibility": "feasible"}
                job = {"id": self.ident, "brief": {"idea": "Miu tìm bạn.", "mode": "motion", "seconds": None,
                                 "duration_mode": "auto"}}
                with patch.object(draft, "_activity"), patch.object(draft, "_measured", return_value=nullcontext()), \
                        patch.object(draft, "_ask", return_value=proposed) as ask:
                    plan = draft._duration_plan(job, {})
                    self.assertTrue(ask.call_args.kwargs["cpu_only"])
                    self.assertEqual(plan["initial_accepted_seconds"], estimate)
                    self.assertEqual(plan["recommended_shot_count"], count)
                    self.assertNotIn("recommended_shot_count", ask.call_args.args[3]["properties"])
                    frames = draft.draft_timeline.planned_timeline(estimate, True, [estimate / count] * count)
                    self.assertEqual(sum(frames), estimate * 24)
                    self.assertTrue(all(24 <= n <= 49 for n in frames))
                    for changes in ({"estimated_duration_seconds": 61}, {"estimated_duration_seconds": 4.5},
                                    {"shots": []}, {"production_feasibility": "over_budget"}):
                        ask.return_value = {**proposed, **changes}
                        with self.assertRaises(ValueError):
                            draft._duration_plan(job, {})
                    ask.return_value = {**proposed, "shots": proposed["shots"][:1]}
                    with self.assertRaisesRegex(ValueError, f"AI trả 1 cảnh. Video {estimate} giây cần"):
                        draft._duration_plan(job, {})

    def test_authored_six_second_script_preserves_two_scenes_across_four_shots(self):
        content = "Cảnh 1 (0–3 giây): Miu mở mắt. Miu nhìn cửa.\nCảnh 2 (3–6 giây): Lan nhặt chiếc hộp."
        brief = {**self.brief, "idea": "Video 6 giây\n" + content, "mode": "motion",
                 "seconds": None, "scene_count": None, "duration_mode": "auto"}
        job = {"id": self.ident, "brief": brief, "storyboard_version": 1, "video_sha": None}
        bindings = {"general.text": {}, "film.storyboard": {}, "image.generate": {}}
        response = {"title": "Kịch bản", "continuity": "Miu and Lan", "description": "Invented action",
                    "image_prompt": "Cat and box", "motion_prompt": "Camera moves", "audio": "Quiet"}
        with (patch.object(draft, "_ask") as planner, patch.object(draft, "_select_cast", return_value={}),
              patch.object(draft, "_script_scene", side_effect=lambda *a, **k: {
                  **response, "description": f"Khoảnh khắc {a[5]}", "motion_prompt": f"Differing moment {a[5]}"}) as storyboard):
            draft._write_planned_board(job, bindings)
            planner.assert_not_called()
        draft._stamp_storyboard(job)
        scenes = job["board"]["scenes"]
        self.assertEqual([scene["frames"] for scene in scenes], [36]*4)
        self.assertEqual([scene["content_scene"] for scene in scenes], [1, 1, 2, 2])
        originals = content.splitlines()
        self.assertEqual([brief["idea"][slice(*scene["script_range"])].strip() for scene in scenes],
                         [originals[0]]*2 + [originals[1]]*2)
        self.assertEqual([scene["description"] for scene in scenes], [scene["shot_description"] for scene in scenes])
        self.assertEqual([call.args[3].strip() for call in storyboard.call_args_list],
                         [originals[0]]*2 + [originals[1]]*2)
        draft._save(job)
        reloaded = draft._read(self.ident)
        self.assertEqual((reloaded["brief"]["duration_mode"], reloaded["brief"]["seconds"],
                          reloaded["brief"]["duration_source"]), ("auto", 6, "script"))
        beats = [call.kwargs["proposed_shot"]["beat"] for call in storyboard.call_args_list]
        self.assertEqual([b["assigned_text"] for b in beats[:2]], ["Miu mở mắt.", "Miu nhìn cửa."])
        self.assertEqual([(b["start_frame_in_scene"], b["end_frame_exclusive"]) for b in beats],
                         [(0, 36), (36, 72), (0, 36), (36, 72)])
        self.assertEqual(beats[1]["previous_shot"]["description"], scenes[0]["shot_description"])
        self.assertEqual(draft.draft_timeline.digest(reloaded), job["storyboard_sha"])
        with self.assertRaisesRegex(ValueError, "giữ thứ tự"):
            draft.act(self.ident, "storyboard-move", {"sha256": job["storyboard_sha"], "index": 0, "target": 2})
        profile = self.motion_profile()
        # Simulate a previously saved board whose description still carries the source excerpt.
        scenes[0]["description"] = originals[0]
        scenes[0].update(asset="image-sha", job_id="image-job", image_key="image-key", attempts=1,
                         motion_job="motion-job", motion_sha="motion-sha")
        scenes[1].update(asset="second-image", job_id="second-job", image_key="second-key", attempts=1,
                         motion_job="second-motion", motion_sha="second-sha")
        draft._stamp_storyboard(job)
        old_sha = job["storyboard_sha"]
        scene_ranges = [scene["script_range"] for scene in scenes]
        draft._save(job)
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {**bindings, "film.motion": profile})),
              patch.object(draft.model_hub, "local_inference_slot", return_value=nullcontext()),
              patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", return_value={"description": "Miu blinks",
                           "image_prompt": scenes[0]["image_prompt"], "motion_prompt": "Miu blinks slowly"}) as rewrite,
              patch.object(draft_motion, "bind", return_value=profile),
              patch.object(draft_motion, "require_resolved_ledger"),
              patch.object(draft_motion, "prepare", return_value=(None, None, None, draft_motion.workflow_sha())),
              patch.object(draft_motion, "run_shot") as motion, patch.object(draft, "_image"),
              patch.object(draft, "_release_idle_image"), patch.object(draft, "_dispatch"),
              patch.object(draft, "_render", return_value="fixture-sha"), patch.object(draft, "_duration_plan") as planner):
            rewritten = draft.act(self.ident, "storyboard-rewrite", {
                "sha256": old_sha, "index": 0, "feedback": "Show the blink"})
            context = rewrite.call_args.args[2]["scene"]
            self.assertEqual(context["description"], scenes[0]["shot_description"])
            self.assertEqual(context["original_script_excerpt"].strip(), originals[0])
            edited = draft.act(self.ident, "storyboard-edit", {
                "sha256": rewritten["storyboard_sha"], "index": 1, "description": "Miu turns toward the door",
                "image_prompt": "Cat looking at a door", "motion_prompt": "Cat turns its head"})
            with self.assertRaisesRegex(ValueError, "Storyboard"):
                draft.act(self.ident, "storyboard-approve", {"sha256": old_sha})
            draft.act(self.ident, "storyboard-approve", {"sha256": edited["storyboard_sha"]})
            saved = draft._read(self.ident)
            self.assertEqual(saved["approved_storyboard_sha"], draft.draft_timeline.digest(saved))
            revised = saved["board"]["scenes"]
            self.assertEqual(saved["brief"]["idea"], brief["idea"])
            self.assertEqual([scene["script_range"] for scene in revised], scene_ranges)
            for scene, description, image, motion_prompt in zip(
                    revised, ("Miu blinks", "Miu turns toward the door"),
                    (scenes[0]["image_prompt"], "Cat looking at a door"),
                    ("Miu blinks slowly", "Cat turns its head")):
                self.assertEqual((scene["shot_description"], scene["description"], scene["image_prompt"],
                                  scene["motion_prompt"]), (description, description, image, motion_prompt))
                self.assertNotIn("motion_job", scene)
                self.assertNotIn("motion_sha", scene)
            self.assertEqual(revised[0]["asset"], "image-sha")
            self.assertEqual(revised[0]["image_key"], "image-key")
            self.assertEqual(saved["storyboard_history"][0]["sha256"], old_sha)
            self.assertEqual(saved["storyboard_history"][0]["checkpoints"][0]["motion_sha"], "motion-sha")
            self.assertIsNone(revised[1]["asset"])
            self.assertIsNone(revised[1]["job_id"])
            self.assertEqual(revised[1]["attempts"], 0)
            self.assertNotEqual(revised[1]["image_key"], "second-key")
            draft._work(draft._read(self.ident), nullcontext())
            planner.assert_not_called()
        self.assertEqual(draft._read(self.ident)["status"], "REVIEW")
        self.assertEqual([call.args[0]["content_scene"] for call in motion.call_args_list], [1, 1, 2, 2])
        self.assertEqual([call.args[0]["motion_prompt"] for call in motion.call_args_list[:2]],
                         ["Miu blinks slowly", "Cat turns its head"])

        alternate = {"output": {"fps": 12, "max_frames": 36, "resolution": [320, 192]}}
        plan = draft._duration_plan({"brief": {**brief, "seconds": None}, "motion_plan": alternate}, {})
        self.assertEqual([shot["script_shot_frames"] for shot in plan["shots"]], [36, 36])

    def test_free_idea_six_seconds_normalizes_ai_three_second_shot_without_retry(self):
        job = {"id": self.ident, "brief": {"idea": "Tạo video dài 6 giây về Miu tìm bạn.", "mode": "motion",
               "seconds": None, "duration_mode": "auto"}}
        shots = [{"action": action, "reason": "Giữ mạch truyện", "suggested_seconds": 3}
                 for action in ("Miu mở cửa", "Miu nhìn quanh", "Miu thấy Lan")]
        proposal = {"estimated_duration_seconds": 18, "shots": shots, "duration_reasoning": "Ba nhịp",
                    "production_feasibility": "feasible"}
        with (patch.object(draft, "_activity"), patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", return_value=proposal) as ask):
            plan = draft._duration_plan(job, {})
        ask.assert_called_once()
        self.assertEqual(ask.call_args.args[2]["requested_seconds"], 6)
        self.assertEqual((plan["initial_accepted_seconds"], plan["duration_source"]), (6, "script"))
        self.assertEqual([shot["action"] for shot in plan["shots"]], [shot["action"] for shot in shots])
        self.assertEqual(draft.draft_timeline.planned_timeline(
            6, True, [shot["suggested_seconds"] for shot in plan["shots"]]), [48, 48, 48])

        job["status"] = "RUNNING"
        response = {"title": "Miu", "continuity": "Cat", "description": "Miu nhìn quanh",
                    "image_prompt": "A cat in a garden", "audio": "Quiet"}
        with (patch.object(draft, "_duration_plan", return_value=plan),
              patch.object(draft, "_select_cast", return_value={}),
              patch.object(draft, "_script_scene", side_effect=lambda *a, **k: dict(response))):
            draft._write_planned_board(job, {"general.text": {}, "film.storyboard": {}, "image.generate": {}})
        saved = draft._read(self.ident)
        self.assertEqual((saved["brief"]["duration_mode"], saved["brief"]["seconds"],
                          saved["brief"]["duration_source"]), ("auto", 6, "script"))
        self.assertEqual(saved["duration_plan"]["estimated_duration_seconds"], 18)

    def test_duration_conflicts_follow_owner_preference(self):
        brief = {"mode": "motion", "duration_mode": "auto", "seconds": None}
        with self.assertRaisesRegex(ValueError, "nhiều thời lượng"):
            draft._duration_plan({"brief": {**brief, "idea": "Video 6 giây. Thời lượng: 8 giây."}}, {})
        idea = "Video 8 giây\nCảnh 1 (3 giây): Miu mở mắt.\nCảnh 2 (3 giây): Lan nhìn Miu."
        with self.assertRaisesRegex(ValueError, "không khớp mục tiêu 8 giây"):
            draft._duration_plan({"brief": {**brief, "idea": idea}}, {})
        manual = {**brief, "idea": idea, "duration_mode": "manual", "seconds": 6}
        self.assertEqual(draft._duration_plan({"brief": manual}, {})["duration_source"], "manual")
        with self.assertRaisesRegex(ValueError, "không khớp mục tiêu 7 giây"):
            draft._duration_plan({"brief": {**manual, "seconds": 7}}, {})

    def test_authored_planner_refuses_duplicate_shot_content(self):
        job = {"id": self.ident, "status": "RUNNING", "brief": {"idea": "Video 6 giây\nCảnh 1 (6 giây): Miu nhảy qua cửa.",
               "mode": "motion", "seconds": None, "duration_mode": "auto"}}
        bindings = {"general.text": {}, "film.storyboard": {}, "image.generate": {}}
        output = {"title": "Miu", "continuity": "Miu at the door", "description": "Miu nhảy",
                  "motion_prompt": "Miu jumps", "image_prompt": "Cat", "audio": "Quiet"}
        with (patch.object(draft, "_select_cast", return_value={}),
              patch.object(draft, "_script_scene", side_effect=lambda *a, **k: dict(output)) as write):
            with self.assertRaisesRegex(ValueError, "AI lặp mô tả hoặc chuyển động ở cảnh 1, shot 2"):
                draft._write_planned_board(job, bindings)
        self.assertEqual(write.call_count, 2)
        self.assertNotIn("board", draft._read(self.ident))

    def test_duration_replans_five_story_beats_into_nine_shots_without_gpu(self):
        job = {"id": self.ident, "brief": {"idea": "Miu đuổi theo bướm rồi quay về nhà.",
               "mode": "motion", "seconds": None, "duration_mode": "auto"}}
        shot = {"action": "Miu nhìn con bướm", "reason": "Theo dõi chuyển động", "suggested_seconds": 1.75}
        plan = {"estimated_duration_seconds": 18, "duration_reasoning": "Giữ đủ nhịp cho hành động.",
                "production_feasibility": "feasible"}
        with (patch.object(draft, "_activity"), patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", side_effect=[{**plan, "shots": [shot]*5},
                                                       {**plan, "shots": [shot]*9}]) as ask):
            result = draft._duration_plan(job, {})
        self.assertEqual(result["recommended_shot_count"], 9)
        self.assertEqual(result["initial_accepted_seconds"], 18)
        frames = draft.draft_timeline.planned_timeline(18, True, [s["suggested_seconds"] for s in result["shots"]])
        self.assertEqual(frames, [48]*9)
        self.assertEqual(ask.call_count, 2)
        self.assertTrue(all(call.kwargs["cpu_only"] for call in ask.call_args_list))
        self.assertEqual(ask.call_args_list[0].args[2]["allowed_shot_counts"][18], (9, 16))
        rules = ask.call_args.args[3]["properties"]
        self.assertEqual(rules["estimated_duration_seconds"]["enum"], [18])
        self.assertEqual(rules["shots"]["minItems"], 9)

    def test_sixty_second_budget_keeps_legacy_layout_and_rejects_excess(self):
        timeline = draft.draft_timeline
        self.assertEqual(timeline.shot_limits(30), (15, 16))
        self.assertEqual(timeline.duration_limits(60, True), (30, 32))
        for count in range(30, 33):
            frames = timeline.planned_timeline(60, True, [2]*count)
            self.assertEqual(sum(frames), 1440)
            self.assertLessEqual(max(frames), 49)
        for count in (29, 33):
            with self.assertRaises(ValueError):
                timeline.planned_timeline(60, True, [2]*count)
        self.assertEqual(sum(timeline.planned_timeline(60, False, [2]*6)), 1440)

    def test_duration_edit_reallocates_frames_and_invalidates_approval(self):
        board = self.board()
        board["scenes"] = [{**scene} for scene in board["scenes"]]
        job = {"id": self.ident, "brief": {**self.brief, "mode": "still", "duration_mode": "manual"},
               "board": board, "video_sha": None, "storyboard_version": 1}
        draft._stamp_storyboard(job)
        old_sha = job["storyboard_sha"]
        job["approved_storyboard_sha"] = old_sha
        draft._save(job)
        with patch.object(draft_motion, "require_resolved_ledger"):
            changed = draft.act(self.ident, "storyboard-duration", {"sha256": old_sha, "seconds": 7})
        self.assertEqual(changed["brief"]["seconds"], 7)
        self.assertEqual(sum(scene["frames"] for scene in changed["board"]["scenes"]), 168)
        self.assertNotEqual(changed["storyboard_sha"], old_sha)
        self.assertNotIn("approved_storyboard_sha", changed)
        self.assertEqual(draft._read(self.ident)["storyboard_history"][0]["sha256"], old_sha)

    def test_script_ranges_keep_exact_text_and_reject_insufficient_capacity(self):
        self.assertFalse(draft._needs_scene_analysis("Một chú mèo đi tìm bạn."))
        text = "Cảnh 1 — Miu nhìn ra cửa sổ 🐱\nMiu: Chào bạn!\n\nCảnh 2 — Miu chạy ra vườn."
        self.assertTrue(draft._needs_scene_analysis(text))
        ranges = draft._script_ranges(text, 2, 12)
        self.assertEqual("".join(text[start:end] for start,end in ranges), text)
        self.assertTrue(text[ranges[1][0]:].startswith("Cảnh 2"))
        with self.assertRaisesRegex(ValueError, "3 cảnh"):
            draft._script_ranges(text+"\nCảnh 3 — Trời tối.", 2, 12)
        with self.assertRaisesRegex(ValueError, "Thời lượng"):
            draft._script_ranges(text+"\nMiu: "+"chào "*50, 2, 6)

    def test_long_script_analysis_uses_bounded_excerpts_before_storyboard(self):
        source = "Cảnh 1 — Miu\n" + "Miu nhìn ra cửa sổ. 🐱\n" * 140 + "\nCảnh 2 — Miu chạy ra vườn."
        job = {"id": self.ident, "status": "RUNNING", "brief":{
            **self.brief, "idea": source}}
        provider = {"provider":"ollama", "model":"fixture"}
        excerpts = []
        def respond(profile, instructions, data, schema, comfy):
            if "excerpt" in data:
                excerpts.append(data["excerpt"])
                self.assertLessEqual(len(data["excerpt"]), 900)
                return {"facts": "Miu chờ bên cửa sổ."}
            self.assertLess(len(str(data)), len(source))
            return {"title":"Miu", "continuity":"Orange cat", "description":"Miu đợi",
                    "image_prompt":"Orange cat by a window", "audio":"Yên tĩnh"}
        with (patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", side_effect=respond)):
            draft._write_board(job, {"film.storyboard":provider, "image.generate":{}})
        board = draft._read(self.ident)["board"]
        self.assertEqual(len(board["scenes"]), 2)
        self.assertEqual("".join(excerpts), source[:board["scenes"][1]["script_range"][0]])
        self.assertEqual("".join(source[start:end] for start,end in
                                 (scene["script_range"] for scene in board["scenes"])), source)

    def test_long_vietnamese_script_http_sqlite_roundtrip_and_limit(self):
        client = owner_http_fixture.OwnerHttpFixture()
        client.setUp()
        self.addCleanup(client.doCleanups)
        client.server.allow_external_actions = True
        client.login()
        prefix = "Cảnh 1 — Miu nhìn ra cửa sổ.\nMiu: Chào bạn!\n"
        suffix = "\n\nCảnh 2 — Miu chạy ra vườn.\n"
        source = prefix + "🐱" * (20_000 - len(prefix) - len(suffix)) + suffix
        body = {**self.brief, "id":self.ident, "idea":source}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {})), patch.object(draft.render, "_ffmpeg"),
              patch.object(draft, "_dispatch")):
            status, result, _ = client.req("POST", "/api/film/drafts/start", body)
            self.assertEqual(status, 200, result.get("message"))
            self.assertEqual(result["brief"]["idea"], source)
            status, result, _ = client.req("GET", "/api/film/drafts")
            self.assertEqual(status, 200)
            self.assertEqual(result["drafts"][0]["brief"]["idea"], source)
            status, error, _ = client.req("POST", "/api/film/drafts/start",
                                         {**body, "idea":source+"đ"})
            self.assertEqual(status, 400)
            self.assertIn("20,000", error["message"])

    def test_submission_validation_and_idempotence(self):
        with self.assertRaises(ValueError):
            draft.submit({"id": self.ident, **self.brief, "ratio": "4:3"})
        draft._save({"id": self.ident, "brief": self.brief, "status": "RUNNING"})
        self.assertEqual(draft.submit({"id": self.ident, **self.brief})["id"], self.ident)
        with self.assertRaises(ValueError):
            draft.submit({"id": self.ident, **self.brief, "idea": "Khác"})
        self.assertEqual(len(draft.list_drafts()), 1)

    def test_list_includes_an_older_draft_updated_after_the_newest_thirty(self):
        old = {"id": self.ident, "brief": self.brief, "status": "REVIEW",
               "created_at": "2026-01-01T00:00:00+00:00"}
        with patch.object(draft.visual_jobs, "_now", return_value="2026-01-01T00:00:00+00:00"):
            draft._save(old)
        with patch.object(draft.visual_jobs, "_now", return_value="2026-01-02T00:00:00+00:00"):
            for index in range(30):
                draft._save({**old, "id": f"{index:032x}", "status": "FAILED"})
        with patch.object(draft.visual_jobs, "_now", return_value="2026-01-03T00:00:00+00:00"):
            draft._save(old)
        jobs = draft.list_drafts()
        self.assertEqual(len(jobs), 30)
        self.assertEqual(jobs[0]["id"], self.ident)

    def test_motion_http_to_verified_mp4_without_gpu(self):
        self._motion_http_to_verified_mp4(legacy=False)

    def test_legacy_approved_motion_http_resumes_without_regenerating_checkpoints(self):
        self._motion_http_to_verified_mp4(legacy=True)

    def _motion_http_to_verified_mp4(self, *, legacy):
        motion = draft_motion.motion_comfy
        runner = draft_motion
        ltx = runner.motion_ltx
        client = owner_http_fixture.OwnerHttpFixture()
        client.setUp()
        self.addCleanup(client.doCleanups)
        client.server.allow_external_actions = True
        client.login()
        body = {**self.brief, "id": self.ident, "seconds": 4, "mode": "motion"}
        route = "/api/film/drafts/start"
        self.assertEqual(client.req("POST", route, {**body, "seconds": 6})[0], 400)
        profile = {"id": "selected_by_registry", "provider": "comfyui", "model": ltx.CHECKPOINT, "enabled": True,
                   "motion_encoder": str(self.root / ltx.ENCODER), "base_url": "http://127.0.0.1:8188"}
        image_profile = flux_profile()
        approved_revision = self.seed_registry(image_profile, profile)
        output = self.root / "output"
        output.mkdir()
        asset = b"FLUX fixture"
        calls = []
        latest = {}

        def provider(path, *, body=None, timeout=6):
            if path == "/prompt":
                self.assert_registry_writer_blocked()
                calls.append("motion")
                graph = body["prompt"]
                self.assertEqual(graph["1"]["inputs"]["ckpt_name"], profile["model"])
                self.assertEqual(graph["6"]["inputs"]["length"], 49)
                file = graph["13"]["inputs"]["filename_prefix"] + "_00001_.mp4"
                (output / file).write_bytes(b"MP4 fixture" * 150)
                key = str(uuid4())
                latest[key] = {"status": {"completed": True, "status_str": "success"},
                               "outputs": {"13": {"images": [{"filename": file, "type": "output", "subfolder": ""}]}}}
                return {"prompt_id": key}
            with closing(sqlite3.connect(draft.model_hub.DB_PATH, timeout=0)) as conn:
                conn.execute("BEGIN IMMEDIATE")
            return {path.split("/")[-1]: latest[path.split("/")[-1]]}

        def image(*args, **kwargs):
            self.assertEqual(kwargs["production_profile"], image_profile)
            calls.append("image")
            return {"status": "ASSET_READY"}

        def ffmpeg(command, **kwargs):
            if "-filter_complex" in command:
                calls.append("render")
                self.assertNotIn("zoompan", " ".join(command))
                self.assertEqual(sum(str(arg).endswith("_00001_.mp4") for arg in command), 0)
                self.assertEqual(sum(Path(arg).name == "clip.mp4" for arg in command), 2)
                Path(command[-1]).write_bytes(b"MP4 fixture" * 150)
            return SimpleNamespace(stdout="frame=96\n")

        def storyboard(job, bindings):
            self.assertEqual(bindings["general.text"]["model"], "planner:8b")
            self.assertEqual(bindings["film.storyboard"]["model"], "writer:8b")
            self.assertNotIn("character.select", bindings)
            job.update(board=draft._story(self.board(), 2, 4, {"cat": {}}),
                       cast={"cat": {"name": "Miu", "appearance": "orange cat"}})

        patches = (patch.object(draft, "_dispatch"), patch.object(draft, "_write_board", side_effect=storyboard),
              patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_release_idle_image"),
              patch.object(flux_runtime, "generate", side_effect=image),
              patch.object(draft.visual_jobs, "open_image_for_job",
                           side_effect=lambda _: nullcontext((io.BytesIO(asset), draft._sha(asset)))),
              patch.object(draft.render, "_ffmpeg", return_value="ffmpeg"),
              patch.object(draft.render, "_run_process", side_effect=ffmpeg),
              patch.object(runner.render, "find_media_tool", return_value="fixture"),
              patch.object(motion, "DB", self.root/"motion.sqlite3"), patch.object(motion, "FILMS", self.root/"films"),
              patch.object(runner.comfy_service, "RUNTIME_DIR", self.root),
              patch.object(runner.comfy_service, "_settings", return_value={"port": 8188, "install_root": self.root}),
              patch.object(runner.comfy_service, "_probe", return_value=None),
              patch.object(runner.comfy_service, "status", return_value={"managed": True}),
              patch.object(runner.comfy_service, "ensure_running"),
              patch.object(runner.comfy_service, "require_idle_queue"),
              patch.object(runner.comfy_service, "require_other_queue_idle"),
              patch.object(ltx, "verify_weights"), patch.object(ltx, "check_runtime"),
              patch.object(ltx, "read_source", return_value=asset),
              patch.object(ltx, "upload_source", return_value="fixture.png"),
              patch.object(motion, "health", return_value={"status": "GPU_DETECTED_UNBENCHMARKED"}),
              patch.object(motion.draft_resources, "require_gpu"),
              patch.object(motion, "_json_request", side_effect=provider),
              patch.object(runner.motion_verify, "_probe", return_value={"codec": "h264", "width": 512,
                  "height": 288, "frames_decoded": 49, "fps": 24, "duration_seconds": 2.042}))
        with ExitStack() as stack:
            for fixture in patches:
                stack.enter_context(fixture)
            response, _, _ = client.req("POST", route, body)
            self.assertEqual(response, 200)
            draft._work(draft._read(self.ident), nullcontext())
            job = draft._read(self.ident)
            self.assertEqual(job["status"], "STORYBOARD_REVIEW", job.get("error"))
            self.assertEqual(calls, [])
            if legacy:
                del job["studio_plan"]
                draft._stamp_storyboard(job)
                draft._save(job)
            approval = route.removesuffix("/start") + f"/{self.ident}/storyboard-approve"
            self.assertEqual(client.req("POST", approval, {"sha256": "stale"})[0], 400)
            if not legacy:
                _, routes = draft.model_hub.draft_routes()
                writer = routes["film.storyboard"]
                self.registry_change("SAVE_MODEL_PROFILE", profile={**writer, "model": "replaced:8b"})
                status, rejected, _ = client.req("POST", approval, {"sha256": job["storyboard_sha"]})
                self.assertEqual(status, 400)
                self.assertIn("film.storyboard", rejected["message"])
                self.assertNotIn("approved_storyboard_sha", draft._read(self.ident))
                self.registry_change("ROLLBACK_MODEL_HUB", target_revision=approved_revision)
            self.assertEqual(client.req("POST", approval, {"sha256": job["storyboard_sha"]})[0], 200)
            pinned = draft._read(self.ident)
            if legacy:
                del pinned["approved_motion_environment"]
                draft._save(pinned)
            self.assertEqual(pinned["approved_storyboard_sha"], draft.draft_timeline.digest(pinned))
            changed_image = json.loads(json.dumps(image_profile))
            changed_image["flux"]["workflow"]["6"]["inputs"]["text"] = "changed"
            for changed, capability in (
                (changed_image, "image.generate"),
                ({**profile, "motion_encoder": str(self.root / "alternate.safetensors")}, "film.motion"),
                ({**profile, "enabled": False}, "film.motion"),
            ):
                with self.subTest(capability=capability, changed=changed["id"]):
                    self.registry_change("SAVE_MODEL_PROFILE", profile=changed)
                    draft._work(draft._read(self.ident), nullcontext())
                    blocked = draft._read(self.ident)
                    self.assertEqual(blocked["status"], "FAILED")
                    self.assertRegex(blocked["error"], capability + "|model gốc")
                    self.assertEqual(blocked["approved_storyboard_sha"], pinned["approved_storyboard_sha"])
                    self.assertEqual(calls, [])
                    self.registry_change("ROLLBACK_MODEL_HUB", target_revision=approved_revision)
            self.registry_change("SAVE_MODEL_PROFILE", profile={
                "id": "unrelated", "provider": "ollama", "model": "unrelated:latest", "enabled": True,
                "base_url": "http://127.0.0.1:11434"})
            replacement = {**image_profile, "id": "replacement_flux"}
            self.registry_change("SAVE_MODEL_PROFILE", profile=replacement)
            self.registry_change("SET_MODEL_ROUTE", task_id="image.generate", model_ref=replacement["id"])
            with self.assertRaisesRegex(ValueError, "image.generate|model gốc"):
                draft.act(self.ident, "resume", {})
            self.registry_change("SET_MODEL_ROUTE", task_id="image.generate", model_ref=image_profile["id"])
            runner.comfy_service.ensure_running.side_effect = runner.comfy_service.StartupError("COMFYUI_UNAVAILABLE")
            draft._work(draft._read(self.ident), nullcontext())
            offline = draft._read(self.ident)
            self.assertEqual(calls, ["image", "image"])
            self.assertEqual(offline["approved_storyboard_sha"], pinned["approved_storyboard_sha"])
            self.assertTrue(all(scene["asset"] and not scene.get("motion_job") for scene in offline["board"]["scenes"]))
            def change_encoder_before_guard(port):
                self.registry_change("SAVE_MODEL_PROFILE", profile={
                    **profile, "motion_encoder": str(self.root / "racing-encoder.safetensors")})
            runner.comfy_service.ensure_running.side_effect = change_encoder_before_guard
            draft._work(draft._read(self.ident), nullcontext())
            blocked = draft._read(self.ident)
            self.assertRegex(blocked["error"], "film.motion|model gốc")
            self.assertEqual(calls, ["image", "image"])
            self.assertTrue(all(not scene.get("motion_job") for scene in blocked["board"]["scenes"]))
            self.registry_change("ROLLBACK_MODEL_HUB", target_revision=approved_revision)
            runner.comfy_service.ensure_running.side_effect = None
            if legacy:
                runner.comfy_service.ensure_running.side_effect = [
                    None, runner.comfy_service.StartupError("COMFYUI_UNAVAILABLE")]
                draft._work(draft._read(self.ident), nullcontext())
                checkpoint = draft._read(self.ident)
                first = checkpoint["board"]["scenes"][0]
                self.assertTrue(first["motion_sha"])
                self.assertEqual(calls, ["image", "image", "motion"])
                self.registry_change("SAVE_MODEL_PROFILE", profile=replacement)
                self.registry_change("ROLLBACK_MODEL_HUB", target_revision=approved_revision)
                runner.comfy_service.ensure_running.side_effect = None

                def resume_now(job, slot):
                    draft._work(job, slot)
                    return draft._read(job["id"])

                with patch.object(draft, "_start", side_effect=resume_now):
                    status, resumed, _ = client.req("POST", approval.replace("storyboard-approve", "resume"), {})
                self.assertEqual((status, resumed["status"]), (200, "REVIEW"))
                self.assertEqual(resumed["approved_storyboard_sha"], pinned["approved_storyboard_sha"])
                self.assertEqual(resumed["board"]["scenes"][0], first)
            else:
                draft._work(draft._read(self.ident), nullcontext())
            job = draft._read(self.ident)
            self.assertEqual(job["status"], "REVIEW", job.get("error"))
            self.assertTrue(job["video_sha"])
            self.assertTrue(all(scene.get("motion_sha") for scene in job["board"]["scenes"]))
            self.assertEqual(calls, ["image", "image", "motion", "motion", "render"])
            self.assertEqual(client.req("GET", f"/api/film/drafts/{self.ident}/motion-0")[0], 200)
            self.assertTrue(draft.video_path(job).with_suffix(".receipt.json").is_file())
            before = job["board"]["scenes"][1]["motion_sha"]
            edit = approval.replace("storyboard-approve", "storyboard-edit")
            fields = {"sha256": job["storyboard_sha"], "index": 0, "description": "Miu looks at the window",
                      "image_prompt": "An orange tabby cat in a forest", "motion_prompt": "Cat turns its head",
                      "caption": "Miu nhìn ra cửa sổ."}
            self.assertEqual(client.req("POST", edit, fields)[0], 200)
            revised = draft._read(self.ident)
            self.assertEqual(revised["storyboard_version"], 2)
            self.assertEqual(revised["status"], "STORYBOARD_REVIEW")
            self.assertNotIn("approved_storyboard_sha", revised)
            self.assertEqual(revised["board"]["scenes"][1]["motion_sha"], before)
            self.assertEqual(client.req("POST", approval, {"sha256": job["storyboard_sha"]})[0], 400)
            self.assertEqual(client.req("POST", approval, {"sha256": revised["storyboard_sha"]})[0], 200)
            draft._work(draft._read(self.ident), nullcontext())
            result = draft._read(self.ident)
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(calls[-3:], ["image", "motion", "render"])
            self.assertEqual(client.req("GET", f"/api/film/drafts/{self.ident}/captions")[0], 200)
            current_video = draft.video_path(result)
            self.assertTrue(current_video.with_name("draft-v01.mp4").is_file())
            with current_video.open("rb") as stream:
                draft.verify_video(result, stream)
            current_video.with_suffix(".receipt.json").write_text("{}")
            with current_video.open("rb") as stream, self.assertRaisesRegex(ValueError, "receipt hash"):
                draft.verify_video(result, stream)

    def test_motion_timeline_is_exact_without_extending_ltx_output(self):
        for seconds, minimum, maximum in ((4, 2, 2), (6, 3, 3), (15, 8, 9)):
            for scene_count in {minimum, maximum}:
                timeline = draft.draft_timeline.timeline(seconds, scene_count)
                self.assertEqual(sum(timeline), seconds * 24)
                self.assertEqual(len(timeline), scene_count)
                self.assertLessEqual(max(timeline), 49)
        for seconds in (60,):
            with self.assertRaises(ValueError):
                draft.draft_timeline.timeline(seconds, 9)

    def test_30_second_storyboard_uses_ai_count_and_preserves_script_order(self):
        text = "\n\n".join(f"Cảnh {i} — Miu mở cánh cửa rồi nhìn quanh." for i in range(1, 16))
        job = {"id": self.ident, "status": "RUNNING", "storyboard_version": 1,
               "brief": {"idea": text, "seconds": 30, "mode": "motion", "scene_count": 15, "ratio": "16:9"}}
        provider = {"provider": "ollama", "model": "fixture"}
        bindings = {"general.text": provider, "film.storyboard": provider, "image.generate": {}}
        with (patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", return_value={"outline": "Miu waits and checks each door.", "scene_count": 16}),
              patch.object(draft, "_script_scene", side_effect=lambda *args: {
                  "title": "Miu", "continuity": "orange tabby", "description": "Cat opens the door",
                  "image_prompt": "A cat by the door", "audio": "silent", "duration_weight": 1 + args[-1]%3})):
            draft._write_board(job, bindings)
        draft._stamp_storyboard(job)
        scenes = job["board"]["scenes"]
        self.assertEqual(len(scenes), 16)
        self.assertEqual(sum(s["frames"] for s in scenes), 720)
        self.assertTrue(all(40 <= s["frames"] <= 49 for s in scenes))
        self.assertGreater(len({s["frames"] for s in scenes}), 1)
        self.assertEqual("".join(text[start:end] for start,end in (s["script_range"] for s in scenes)), text)
        self.assertEqual(job["status"], "STORYBOARD_REVIEW")
        self.assertEqual(sum(draft.draft_timeline.timeline(30, 15)), 720)
        for invalid in (14, 17):
            with self.assertRaises(ValueError):
                draft.draft_timeline.timeline(30, invalid)

    def test_new_still_draft_also_waits_for_storyboard_approval(self):
        def storyboard(job, _):
            job.update(board=draft._story(self.board(), 2, 6, {"cat": {}}), cast={})
        with (patch.object(draft.model_hub, "draft_routes", return_value=(4, {"image.generate": {}})),
              patch.object(draft, "_write_board", side_effect=storyboard),
              patch.object(draft, "_dispatch"), patch.object(draft, "_image") as image,
              patch.object(draft_motion, "require_resolved_ledger")):
            job = draft.submit({"id": self.ident, **self.brief})
            draft._work(job, nullcontext())
            self.assertEqual(draft._read(self.ident)["status"], "STORYBOARD_REVIEW")
            image.assert_not_called()

    def test_motion_failure_does_not_render_or_dispatch_another_shot(self):
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion", "seconds": 4},
               "status": "RUNNING", "motion_revision": 8,
               "board": draft._story(self.board(), 2, 4, {"cat": {}}), "cast": {}}
        def fail(*args, **kwargs):
            args[0]["motion_job"] = "b" * 32
            args[4]()
            raise ValueError("Motion dispatch requires reconciliation")
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": {}, "film.motion": self.motion_profile()})),
              patch.object(draft, "_image"), patch.object(draft, "_release_idle_image"),
              patch.object(draft_motion, "bind", return_value={"provider": "comfyui", "model": "fixture"}),
              patch.object(draft_motion, "require_resolved_ledger"),
              patch.object(draft_motion, "prepare", return_value=(None, None, None, draft_motion.workflow_sha())),
              patch.object(draft, "_dispatch"),
              patch.object(draft_motion, "run_shot", side_effect=fail) as run,
              patch.object(draft, "_render") as render):
            draft._work(job, nullcontext())
        run.assert_called_once()
        render.assert_not_called()
        stored = draft._read(self.ident)
        self.assertEqual(stored["status"], "FAILED")
        self.assertEqual(stored["stage"], "MOTION")
        self.assertEqual(stored["board"]["scenes"][0]["motion_job"], "b" * 32)
        self.assertIsNone(stored.get("video_sha"))

    def test_external_comfy_collects_only_the_expected_motion_output(self):
        runner = draft_motion
        job = "b" * 32
        filename = f"af_motion_{job}_00001_.mp4"
        payload = b"video fixture" * 100

        def inspect(**kwargs):
            self.assertEqual(kwargs["job_id"], job)
            path = kwargs["output_dir"] / kwargs["filename"]
            self.assertEqual(path.read_bytes(), payload)
            return {"clip_sha256": "fixture"}

        with (patch.object(runner.comfy_service, "status", return_value={"managed": False}),
              patch.object(runner.http.client, "HTTPConnection") as transport,
              patch.object(runner.motion_verify, "import_clip", side_effect=inspect) as importer):
            response = transport.return_value.getresponse.return_value
            response.status = 200
            response.read1.side_effect = [payload, b""]
            with self.assertRaisesRegex(ValueError, "does not match"):
                runner._collect_clip(job, "../outside.mp4", self.root)
            transport.assert_not_called()
            self.assertEqual(runner._collect_clip(job, filename, self.root), {"clip_sha256": "fixture"})
            transport.assert_called_once_with("127.0.0.1", 8188, timeout=5)
            transport.return_value.request.assert_called_once_with(
                "GET", f"/view?filename={filename}&type=output&subfolder=")
            importer.assert_called_once()
        self.assertFalse(list(self.root.glob("motion-output-*")))

    def test_motion_cancel_targets_provider_and_disconnection_can_resume_existing_job(self):
        runner = draft_motion
        provider = str(uuid4())
        scene = {"motion_job": "b"*32}
        prepared = ("film", "plan", self.root/"graph.json", "sha")
        queue = ('{"queue_pending":[],"queue_running":[[0,"' + provider + '"]]}').encode()
        with (patch.object(runner.motion_verify, "_job", return_value={"provider_id": provider}),
              patch.object(runner.motion_comfy, "job_status") as status,
              patch.object(runner.motion_comfy, "submit_shot") as submit,
              patch.object(runner.motion_verify, "inspect_receipt", return_value={"clip_sha256": "verified"}),
              patch.object(runner.comfy_service.comfyui, "request_image_bytes", return_value=queue),
              patch.object(runner.http.client, "HTTPConnection") as transport,
              patch.object(runner.time, "sleep")):
            transport.return_value.getresponse.return_value.status = 200
            status.side_effect = [{"status": "PROVIDER_QUEUED_OR_UNKNOWN"}, TimeoutError()]
            with self.assertRaises(runner.NeedsReconciliation):
                runner.run_shot(scene, 0, prepared, {}, lambda: None, lambda: True)
            request = transport.return_value.request.call_args
            self.assertEqual(request.args, ("POST", "/interrupt"))
            self.assertIn(provider, request.kwargs["body"])
            self.assertEqual(scene, {"motion_job": "b"*32})
            status.side_effect = None
            status.return_value = {"status": runner.motion_verify.TECHNICAL}
            runner.run_shot(scene, 0, prepared, {}, lambda: None, lambda: False)
            self.assertEqual(scene["motion_sha"], "verified")
            submit.assert_not_called()

    def test_storyboard_rejects_unknown_cast_and_distributes_exact_duration(self):
        with self.assertRaisesRegex(ValueError, "unknown character"):
            draft._story(self.board(), 2, 7, {})
        result = draft._story(self.board(), 2, 7, {"cat": {}})
        self.assertEqual([scene["seconds"] for scene in result["scenes"]], [4, 3])

    def test_planning_outline_contract_matches_validation(self):
        job = {"id": self.ident, "status": "RUNNING", "brief": {**self.brief,
            "seconds": 15, "scene_count": 8, "mode": "motion"}}
        bindings = {"general.text": {"provider": "ollama", "model": "fixture"}, "image.generate": {}}
        with (patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", return_value={"outline": "ế" * 701}) as planner):
            with self.assertRaisesRegex(ValueError, "Dàn ý do AI trả về.*700"):
                draft._write_board(job, bindings)
        self.assertNotIn("plan", draft._read(self.ident))
        _, instructions, brief, schema, _ = planner.call_args.args
        self.assertIn("700 characters", instructions)
        self.assertEqual(brief["seconds"], 15)
        self.assertEqual(schema["properties"]["outline"]["maxLength"], 700)

    def test_resume_reuses_previous_asset_and_generates_only_failed_scene(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}),
               "cast": {"cat": {"name": "Mèo", "appearance": "Lông cam"}}}
        folder = draft._folder(self.ident)
        folder.mkdir(parents=True)
        known = b"previously verified scene image"
        (folder / "scene-01.png").write_bytes(known)
        job["board"]["scenes"][0]["asset"] = draft._sha(known)
        draft._save(job)
        profile = flux_profile()
        def missing_output(*args, **kwargs):
            self.assertEqual(draft._read(self.ident)["activity"], {
                "operation": "image", "provider": "comfyui", "model": "fixture.gguf", "scene": 2,
            })
            return {"status": "COMFYUI_STOPPED"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": profile})),
              patch.object(flux_runtime, "generate", side_effect=missing_output) as generate):
            draft._work(job, nullcontext())
            self.assertEqual(job["status"], "FAILED")
            self.assertEqual(job["error"], "ComfyUI scene result: COMFYUI_STOPPED")
            self.assertNotIn("activity", job)
            self.assertEqual(job["board"]["scenes"][1]["attempts"], 1)
            generate.assert_called_once()
        recovered = draft._read(self.ident)
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": profile})),
              patch.object(draft.visual_jobs, "_row", side_effect=KeyError),
              patch.object(flux_runtime, "generate", return_value={"status": "ASSET_READY"}) as generate,
              patch.object(draft.visual_jobs, "open_image_for_job",
                           return_value=nullcontext((io.BytesIO(b"new asset"), draft._sha(b"new asset")))),
              patch.object(draft, "_render", return_value="verified")):
            draft._work(recovered, nullcontext())
            generate.assert_called_once()
            self.assertIn("Lông cam", generate.call_args.args[0])
            self.assertTrue(generate.call_args.kwargs["scene"].endswith("/scene-02"))
        self.assertEqual((folder / "scene-01.png").read_bytes(), known)
        self.assertEqual(draft._read(self.ident)["status"], "REVIEW")

    def test_launcher_error_before_submission_keeps_scene_retry_budget(self):
        job = {"id": self.ident, "brief": self.brief,
               "board": draft._story(self.board(), 2, 6, {"cat": {}}),
               "cast": {"cat": {"name": "Miu", "appearance": "orange cat"}}}
        scene = job["board"]["scenes"][0]
        profile = flux_profile()
        for error in ("COMFYUI_LAUNCHER_REQUIRED", "COMFYUI_ENDPOINT_MISMATCH"):
            with (self.subTest(error=error),
                  patch.object(flux_runtime, "generate",
                               side_effect=draft.comfy_service.StartupError(error))):
                with self.assertRaisesRegex(draft.comfy_service.StartupError, error):
                    draft._image(job, 0, scene, 1, profile)
            self.assertEqual(scene["attempts"], 0)
            self.assertIsNone(scene["job_id"])

    def test_job_waits_on_ram_and_vram_and_preserves_scene_checkpoint(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}), "cast": {}}
        draft._save(job)
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {"image.generate": {}})),
              patch.object(draft, "_image") as image):
            for field, reason in (("ram_available", "RAM_LOW"), ("vram_free_mib", "VRAM_LOW")):
                with self.subTest(reason=reason), patch.dict(self.capacity, {field: 1}):
                    draft._work(job, nullcontext())
                    self.assertEqual(draft._read(self.ident)["status"], "WAITING_RESOURCES")
                    self.assertEqual(draft._read(self.ident)["error"], reason)
            image.assert_not_called()
        self.assertTrue(all(scene["attempts"] == 0 for scene in job["board"]["scenes"]))

    def test_queue_limit_idempotence_and_queued_cancel(self):
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {})), patch.object(draft.render, "_ffmpeg"),
              patch.object(draft, "_queue_limit", return_value=1), patch.object(draft, "_dispatch")):
            submitted = draft.submit({"id": self.ident, **self.brief})
            self.assertEqual(submitted["status"], "QUEUED")
            self.assertEqual(submitted["created_at"], submitted["updated_at"])
            self.assertEqual(draft.submit({"id": self.ident, **self.brief})["id"], self.ident)
            with self.assertRaisesRegex(ValueError, "queue"):
                draft.submit({"id": "b" * 32, **self.brief})
            cancelled = draft.act(self.ident, "cancel", {})
            self.assertEqual(cancelled["status"], "CANCELLED")
            self.assertEqual(draft._read(self.ident)["created_at"], submitted["created_at"])
            self.assertEqual(draft.submit({"id": "b" * 32, **self.brief})["status"], "QUEUED")

    def test_running_cancel_keeps_committed_scene_and_skips_render(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}), "cast": {}}
        draft._save(job)

        def complete_scene(job, index, scene, revision, profile):
            scene["asset"] = "committed"
            draft._save(job)
            draft._cancellation(job["id"], mark=True)

        profile = {**flux_profile(), "base_url": "http://127.0.0.1:8188"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {"image.generate": profile})),
              patch.object(draft.comfy_service, "require_other_queue_idle"),
              patch.object(draft.comfy_service, "require_idle_queue"),
              patch.object(draft, "_image", side_effect=complete_scene) as image,
              patch.object(draft, "_render") as render,
              patch.object(draft, "_release_idle_image") as release):
            draft._work(job, nullcontext())
            image.assert_called_once()
            render.assert_not_called()
            release.assert_called_once_with(profile)
        restored = draft._read(self.ident)
        self.assertEqual(restored["status"], "CANCELLED")
        self.assertEqual(restored["board"]["scenes"][0]["asset"], "committed")

    def test_comfy_offload_skipped_during_commit_pressure(self):
        with (patch.dict(self.capacity, {"commit_used": 31 << 30}),
              patch.object(flux_runtime, "_json") as request):
            self.assertFalse(studio_flux.release_idle_models({"base_url": "http://127.0.0.1:8188"}))
            request.assert_not_called()

    def test_ollama_duration_timeout_reports_provider_without_retry(self):
        profile = {"id": "fixture", "provider": "ollama", "model": "fixture", "base_url": "http://127.0.0.1:11434"}
        with (patch.object(studio_ollama.runtime, "_installed_local_model", return_value=True),
              patch.object(studio_ollama.runtime, "_http_json", side_effect=TimeoutError) as request,
              self.assertRaisesRegex(ValueError, "Ollama không phản hồi trong 300 giây")):
            draft._ask(profile, "Plan", {}, {}, None, cpu_only=True)
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs["timeout"], 300)

    def test_ollama_500_does_not_retry(self):
        profile = {"id": "fixture", "provider": "ollama", "model": "fixture", "base_url": "http://127.0.0.1:11434"}
        with (patch.object(studio_ollama.runtime, "_installed_local_model", return_value=True),
              patch.object(studio_ollama.runtime, "_http_json",
                           side_effect=studio_ollama.runtime.LocalProviderHTTPError(500)) as request,
              self.assertRaisesRegex(draft.ResourceWait, "OLLAMA_RESOURCE_OR_SERVER_ERROR")):
            draft._ask(profile, "Plan", {}, {}, {})
        request.assert_called_once()

    def test_local_render_integrity_and_review_checkpoint(self):
        try:
            from PIL import Image
            draft.render._ffmpeg()
        except (ImportError, RuntimeError):
            self.skipTest("Media extra unavailable")
        for ratio in ("16:9", "9:16"):
            with self.subTest(ratio=ratio):
                job = {"id": self.ident, "brief": {**self.brief, "ratio": ratio}, "status": "REVIEW",
                       "board": draft._story(self.board(), 2, 6, {"cat": {}})}
                folder = draft._folder(self.ident)
                folder.mkdir(parents=True, exist_ok=True)
                for i, scene in enumerate(job["board"]["scenes"], start=1):
                    path = folder / f"scene-{i:02d}.png"
                    Image.new("RGB", (256, 256), (150, i * 50, 80)).save(path)
                    scene["asset"] = draft._sha(path.read_bytes())
                job["video_sha"] = draft._render(job)
                draft._save(job)
                with self.assertRaisesRegex(ValueError, "current draft"):
                    draft.act(self.ident, "approve", {"sha256": "wrong"})
                edited = draft.act(self.ident, "edit", {
                    "index": 1, "description": "Sửa", "image_prompt": "New scene"})
                self.assertEqual(edited["board"]["scenes"][0]["asset"], job["board"]["scenes"][0]["asset"])
                self.assertIsNone(edited["board"]["scenes"][1]["asset"])
                self.assertIsNone(edited["video_sha"])
                draft._save(job)
                result = draft.act(self.ident, "approve", {"sha256": job["video_sha"]})
                self.assertEqual(result["status"], "APPROVED")
