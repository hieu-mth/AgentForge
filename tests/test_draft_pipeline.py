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

from agentforge.features.film_studio import draft_motion, draft_pipeline as draft, studio_ollama, studio_runtime, script_analysis
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
        self.submission = {**self.brief, "scene_count": None, "mode": "still", "duration_mode": "manual"}
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
        for task, ref in {"general.text": text["id"], "film.storyboard": writer["id"],
                          "image.generate": image["id"], "film.motion": motion["id"]}.items():
            self.registry_change("SET_MODEL_ROUTE", task_id=task, model_ref=ref)
        return self.registry_change("SAVE_ORCHESTRATOR", policy=policy)["revision"]

    def test_new_storyboard_without_media_routes_or_image_gpu_and_late_binding(self):
        text = {"id": "owner_writer", "provider": "ollama", "enabled": True,
                "model": "writer:8b", "base_url": "http://127.0.0.1:11434"}
        self.registry_change("SAVE_MODEL_PROFILE", profile=text)
        policy = draft.model_hub.orchestrator_policy.defaults()
        policy["permissions"].update(plan=True, assign_models=True, call_local=True)
        for task in ("general.text", "film.storyboard"):
            self.registry_change("SET_MODEL_ROUTE", task_id=task, model_ref=text["id"])
        self.registry_change("SAVE_ORCHESTRATOR", policy=policy)
        def storyboard(job, bindings):
            self.assertEqual(set(bindings), {"general.text", "film.storyboard"})
            with draft._measured(job, "storyboard"):
                job.update(board=draft._story(self.board(), 2, 6, {"cat": {}}), cast={})
        with (patch.object(draft, "_dispatch"),
              patch.object(draft, "_write_board", side_effect=storyboard),
              patch.object(draft.draft_resources, "require_gpu", side_effect=AssertionError("image GPU gate")),
              patch.object(studio_runtime, "image_adapter", side_effect=AssertionError("image adapter")),
              patch.object(studio_runtime, "motion_artifacts", side_effect=AssertionError("motion adapter")),
              patch.dict(self.capacity, {"vram_free_mib": 0})):
            job = draft.submit({"id": self.ident, **self.submission})
            draft._work(job, nullcontext())
        saved = draft._read(self.ident)
        self.assertEqual(saved["status"], "STORYBOARD_REVIEW", saved.get("error"))
        self.assertTrue(saved["deferred_media_binding"])
        self.assertNotIn("image.generate", saved["studio_plan"])
        sha = saved["storyboard_sha"]
        with self.assertRaises(PermissionError):
            draft.act(self.ident, "storyboard-approve", {"sha256": sha})
        self.assertEqual(draft._read(self.ident), saved)
        policy["permissions"]["run_tools"] = True
        policy["tools"] = ["ffmpeg"]
        self.registry_change("SAVE_ORCHESTRATOR", policy=policy)
        with self.assertRaisesRegex(ValueError, "image.generate"):
            draft.act(self.ident, "storyboard-approve", {"sha256": sha})
        image = flux_profile()
        self.registry_change("SAVE_MODEL_PROFILE", profile=image)
        self.registry_change("SET_MODEL_ROUTE", task_id="image.generate", model_ref=image["id"])
        with patch.object(draft.render, "_ffmpeg"):
            approved = draft.act(self.ident, "storyboard-approve", {"sha256": sha})
        self.assertEqual(approved["status"], "QUEUED")
        self.assertNotIn("deferred_media_binding", approved)
        self.assertEqual(approved["board"], saved["board"])
        self.assertIn("image.generate", approved["studio_plan"])
        self.assertEqual(approved["approved_storyboard_sha"], draft.draft_timeline.digest(approved))
        self.assertNotEqual(approved["approved_storyboard_sha"], sha)

    def test_new_motion_storyboard_does_not_require_motion_profile_before_review(self):
        text = {"id": "owner_writer", "provider": "ollama", "enabled": True,
                "model": "writer:8b", "base_url": "http://127.0.0.1:11434"}
        self.registry_change("SAVE_MODEL_PROFILE", profile=text)
        policy = draft.model_hub.orchestrator_policy.defaults()
        policy["permissions"] = dict.fromkeys(policy["permissions"], True)
        policy["tools"] = ["ffmpeg"]
        for task in ("general.text", "film.storyboard"):
            self.registry_change("SET_MODEL_ROUTE", task_id=task, model_ref=text["id"])
        self.registry_change("SAVE_ORCHESTRATOR", policy=policy)
        def storyboard(job, bindings):
            self.assertNotIn("film.motion", bindings)
            job.update(board=draft._story(self.board(), 2, 4, {"cat": {}}), cast={})
        with (patch.object(draft, "_dispatch"), patch.object(draft, "_write_board", side_effect=storyboard),
              patch.object(studio_runtime, "motion_adapter", side_effect=AssertionError("motion before review"))):
            job = draft.submit({"id": self.ident, **self.submission, "mode": "motion", "seconds": 4})
            draft._work(job, nullcontext())
        saved = draft._read(self.ident)
        self.assertEqual(saved["status"], "STORYBOARD_REVIEW", saved.get("error"))
        self.assertNotIn("motion_plan", saved)
        image = flux_profile()
        motion = {**self.motion_profile(), "enabled": True}
        self.registry_change("SAVE_MODEL_PROFILE", profile=image)
        self.registry_change("SET_MODEL_ROUTE", task_id="image.generate", model_ref=image["id"])
        sha = saved["storyboard_sha"]
        with self.assertRaisesRegex(ValueError, "film.motion"):
            draft.act(self.ident, "storyboard-approve", {"sha256": sha})
        self.registry_change("SAVE_MODEL_PROFILE", profile=motion)
        self.registry_change("SET_MODEL_ROUTE", task_id="film.motion", model_ref=motion["id"])
        with patch.object(draft_motion, "bind", return_value=motion):
            approved = draft.act(self.ident, "storyboard-approve", {"sha256": sha})
        self.assertEqual(approved["approved_motion"], approved["motion_plan"])
        self.assertEqual(approved["approved_storyboard_sha"], draft.draft_timeline.digest(approved))
        self.assertEqual(approved["board"], saved["board"])
        self.assertEqual(approved["status"], "QUEUED")

    def test_explicit_cloud_storyboard_without_media_permission_or_tools(self):
        writer = {"id": "owner_writer", "provider": "ollama", "enabled": True,
                  "model": "writer:8b", "base_url": "http://127.0.0.1:11434"}
        video = {"id": "cloud_video", "provider": "ltx_cloud", "enabled": True,
                 "model": "ltx-2-3-fast", "base_url_env": "LTX_BASE_URL", "api_key_env": "LTX_API_KEY"}
        for profile in (writer, video):
            self.registry_change("SAVE_MODEL_PROFILE", profile=profile)
        for task in ("general.text", "film.storyboard"):
            self.registry_change("SET_MODEL_ROUTE", task_id=task, model_ref=writer["id"])
        policy = draft.model_hub.orchestrator_policy.defaults()
        policy["permissions"].update(plan=True, assign_models=True, call_local=True)
        self.registry_change("SAVE_ORCHESTRATOR", policy=policy)
        from agentforge.features.film_studio import draft_motion_cloud
        def storyboard(job, bindings):
            self.assertEqual(set(bindings), {"general.text", "film.storyboard"})
            job.update(board=draft._story(self.board(), 2, 4, {"cat": {}}), cast={})
        with (patch.object(draft, "_dispatch"),
              patch.object(draft, "_write_board", side_effect=storyboard),
              patch.object(draft, "_image", side_effect=AssertionError("image generation")),
              patch.object(draft_motion_cloud, "bind", side_effect=AssertionError("video readiness")),
              patch.object(draft_motion_cloud.ltx, "_request", side_effect=AssertionError("cloud video API")),
              patch.object(draft.render, "_ffmpeg", side_effect=AssertionError("FFmpeg"))):
            job = draft.submit({"id": self.ident, **self.submission, "mode": "motion", "seconds": 4,
                                "scene_count": None, "duration_mode": "manual",
                                "route_strategy": "cloud", "max_cloud_seconds": 12})
            draft._work(job, nullcontext())
            saved = draft._read(self.ident)
            self.assertEqual(saved["status"], "STORYBOARD_REVIEW", saved.get("error"))
            self.assertEqual(saved["production_plan"]["motion_ref"], video["id"])
            self.assertNotIn("cloud_motion_seconds", saved)
            with self.assertRaises(PermissionError):
                draft.act(self.ident, "storyboard-approve", {"sha256": saved["storyboard_sha"]})

    def test_unexpected_error_has_safe_diagnostic_code(self):
        job = {"id": self.ident, "stage": "PLANNING", "status": "RUNNING",
               "brief": {"duration_mode": "auto"}}
        with (patch.object(draft, "_dispatch"),
              patch.object(draft, "_studio_bindings", side_effect=RuntimeError("secret-provider-payload")),
              self.assertLogs(draft.LOG, level="ERROR") as logs):
            draft._work(job, nullcontext())
        saved = draft._read(self.ident)
        self.assertEqual(saved["error_code"], "STUDIO_UNEXPECTED_RUNTIMEERROR")
        self.assertNotIn("secret-provider-payload", str(saved))
        self.assertNotIn("secret-provider-payload", str(logs.output))

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
            **draft.model_hub.ADAPTERS["anthropic"]["environment_defaults"]})
        saved = draft._read(self.ident)
        current, _, legacy = draft._studio_bindings(saved)
        self.assertGreater(current, revision)
        self.assertEqual(legacy, revision)
        self.assertEqual(draft.draft_timeline.digest(saved), saved["approved_storyboard_sha"])
        self.assertNotIn("studio_plan", saved)
        self.registry_change("SET_MODEL_ROUTE", task_id="general.text", model_ref="cloud_config")
        with self.assertRaisesRegex(ValueError, "Model Studio đã thay đổi|model gốc"):
            draft._studio_bindings(saved)
        self.registry_change("RESET_MODEL_ROUTE", task_id="general.text")
        self.registry_change("DELETE_MODEL_PROFILE", profile_id="owner_planner")
        with self.assertRaisesRegex(ValueError, "chưa phân công"):
            draft._studio_bindings(saved)
        self.registry_change("SAVE_MODEL_PROFILE", profile={
            "id": "owner_planner", "provider": "ollama", "enabled": True,
            "model": "planner:8b", "base_url": "http://127.0.0.1:11434"})
        self.registry_change("SET_MODEL_ROUTE", task_id="general.text", model_ref="owner_planner")
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
                  "characters": [{"id": "cat", "name": "Miu", "appearance": "Orange cat", "version": 3}]}),
              patch.object(draft, "_activity"), patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", return_value={"ids": ["cat"]}) as ask):
            self.assertEqual(draft._select_cast(job, bindings, "A cat")["cat"]["reference_version"], 3)
            self.assertEqual(ask.call_args.args[0]["id"], "owner_story")
            self.registry_change("SET_MODEL_ROUTE", task_id="character.select", model_ref="owner_planner")
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
        with (patch.object(studio_runtime.registry, "REGISTRATIONS",
                           (*studio_runtime.registry.REGISTRATIONS,
                            studio_runtime.registry.Registration("video", lambda: adapter))),
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

    def test_runtime_selection_uses_registry_provider_and_refuses_unknown_adapter(self):
        transport = studio_ollama.runtime
        with (patch.object(transport, "_installed_local_model", return_value=True),
              patch.object(transport, "_http_json", return_value={
                  "done": True, "message": {"content": '{"ready": true}'}}) as call):
            for name in ("planner-alpha:8b", "planner-beta:4b"):
                profile = {"id": "owner_planner", "provider": "ollama", "model": name,
                           "base_url": "http://127.0.0.1:11434"}
                self.assertEqual(draft._ask(profile, "Plan", {}, {}, None), {"ready": True})
                self.assertEqual(call.call_args.kwargs["payload"]["model"], name)
            with self.assertRaisesRegex(ValueError, "supported text API or local runtime"):
                draft._ask({"provider": "unsupported"}, "Plan", {}, {}, None)
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

    def test_regenerate_completed_still_shot_preserves_other_checkpoint_and_history(self):
        board = self.board()
        board["scenes"] = [dict(scene, asset=str(i)*64, job_id=str(i)*32, attempts=1)
                           for i, scene in enumerate(board["scenes"], 1)]
        job = {"id": self.ident, "brief": self.brief.copy(), "board": board, "cast": {},
               "storyboard_version": 1, "video_sha": None}
        draft._stamp_storyboard(job)
        old_sha = job["storyboard_sha"]
        job.update(status="REVIEW", video_sha="f"*64, approved_storyboard_sha=old_sha)
        draft._save(job)
        other = dict(job["board"]["scenes"][1])
        request = {"sha256": old_sha, "index": 0, "scope": "image"}
        with patch.object(draft_motion, "require_resolved_ledger"):
            with self.assertRaisesRegex(ValueError, "Phạm vi"):
                draft.act(self.ident, "storyboard-regenerate", dict(request, scope="motion"))
            result = draft.act(self.ident, "storyboard-regenerate", request)
            first, second = result["board"]["scenes"]
            self.assertIsNone(first["asset"])
            self.assertIsNone(first["job_id"])
            self.assertEqual(first["attempts"], 0)
            self.assertEqual(second, other)
            self.assertEqual(result["storyboard_version"], 2)
            self.assertEqual(result["status"], "STORYBOARD_REVIEW")
            self.assertNotIn("approved_storyboard_sha", result)
            self.assertIsNone(result["video_sha"])
            self.assertEqual(result["storyboard_history"][0]["video_sha"], "f"*64)
            self.assertEqual(result["storyboard_history"][0]["checkpoints"][0]["asset"], "1"*64)
            self.assertEqual(result["storyboard_sha"], draft.draft_timeline.digest(result))
            with self.assertRaisesRegex(ValueError, "Storyboard đã thay đổi"):
                draft.act(self.ident, "storyboard-regenerate", request)
            with self.assertRaisesRegex(ValueError, "Chỉ tạo lại cảnh"):
                draft.act(self.ident, "storyboard-regenerate",
                          dict(request, sha256=result["storyboard_sha"]))

    def test_regenerate_completed_motion_shot_keeps_image_and_pins_new_seed(self):
        board = self.board()
        board["scenes"] = [dict(scene, asset=str(i)*64, job_id=str(i)*32, attempts=1,
                                motion_sha=str(i+2)*64, motion_job=str(i+2)*32)
                           for i, scene in enumerate(board["scenes"], 1)]
        output = studio_runtime.LEGACY_MOTION_OUTPUT
        motion_plan = {"adapter": draft_motion.ADAPTER_ID, "encoder_path_sha": "fixture",
                       "output": {"fps": output.fps, "max_frames": output.max_frames,
                                  "resolution": list(output.resolution)}}
        job = {"id": self.ident, "brief": dict(self.brief, mode="motion", seconds=4),
               "board": board, "cast": {}, "storyboard_version": 1, "video_sha": None,
               "motion_plan": motion_plan}
        draft._stamp_storyboard(job)
        job.update(status="REVIEW", video_sha="f"*64, approved_storyboard_sha=job["storyboard_sha"])
        draft._save(job)
        other = dict(job["board"]["scenes"][1])
        with patch.object(draft_motion, "require_resolved_ledger"):
            result = draft.act(self.ident, "storyboard-regenerate",
                               {"sha256": job["storyboard_sha"], "index": 0, "scope": "motion"})
        first, second = result["board"]["scenes"]
        self.assertEqual(first["asset"], "1"*64)
        self.assertEqual(first["job_id"], "1"*32)
        self.assertNotIn("motion_job", first)
        self.assertNotIn("motion_sha", first)
        self.assertEqual(first["motion_seed"], 1042)
        self.assertEqual(second, other)
        self.assertEqual(result["storyboard_history"][0]["checkpoints"][0]["motion_sha"], "3"*64)
        digest = result["storyboard_sha"]
        self.assertEqual(draft.draft_timeline.digest(result), digest)
        first["motion_seed"] += 1
        self.assertNotEqual(draft.draft_timeline.digest(result), digest)

    def test_finished_drafts_are_read_only_for_scene_edits(self):
        for status in ("APPROVED", "REJECTED", "CANCELLED"):
            with self.subTest(status=status):
                job = {"id": self.ident, "brief": self.brief, "board": self.board(), "status": status}
                draft._save(job)
                with self.assertRaisesRegex(ValueError, "Draft cannot be resumed"):
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
            conn = motion._db(ledger, write=True)
            try:
                with conn:
                    conn.execute("INSERT INTO motion_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 ("c"*32, f"d-{self.ident}-v2", "shot", "a"*64, "b"*64,
                                  "d"*64, 1, None, "SUBMITTED", "created", "updated"))
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
                         ["Miu mở mắt.", "Miu nhìn cửa.", "Lan nhặt chiếc hộp.", "Lan nhặt chiếc hộp."])
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

    def test_global_requirements_after_an_authored_action_are_not_action_beats(self):
        result = script_analysis.scene_beats(
            "Cảnh 3 (10–15 giây): Mèo nhìn ra cửa sổ, sau đó vẫy đuôi. "
            "**Yêu cầu xuyên suốt:**\n- Giữ nhất quán căn phòng.\n"
            "- AI tự quyết định góc máy.\n- Không chữ.", last=True)
        self.assertEqual(result["actions"], ["Mèo nhìn ra cửa sổ", "vẫy đuôi."])
        self.assertEqual(result["camera"], [])
        self.assertEqual(result["global_constraints"],
                         ["Giữ nhất quán căn phòng.", "AI tự quyết định góc máy.", "Không chữ."])
        scene = script_analysis.scene_beats(
            "Cảnh 1 (0–5 giây): Mèo nằm bên cửa sổ. Ánh nắng buổi sáng chiếu nhẹ vào căn phòng. "
            "Bướm bay qua trước mặt mèo.", last=False)
        self.assertEqual(scene["actions"], ["Mèo nằm bên cửa sổ.", "Bướm bay qua trước mặt mèo."])
        self.assertEqual(scene["constraints"], ["Ánh nắng buổi sáng chiếu nhẹ vào căn phòng."])

    def test_creative_production_review_edit_and_dispatch_use_persisted_segment_plan(self):
        profile = self.motion_profile()
        bindings = {"general.text": {}, "film.storyboard": {}, "image.generate": {}, "film.motion": profile}
        job = {"id": self.ident, "status": "RUNNING", "video_sha": None, "storyboard_version": 1,
               "creative_director_version": 1, "brief": {
                   "idea": "Video 6 giây\nCảnh 1 (0–3 giây): Mở cửa.\nCảnh 2 (3–6 giây): Bước vào.",
                   "seconds": None, "scene_count": None, "ratio": "16:9", "mode": "motion", "duration_mode": "auto"}}
        job["motion_plan"] = studio_runtime.motion_identity(draft_motion, profile)
        job["studio_plan"] = studio_runtime.routing_identity(bindings, moving=True)
        shot = {"actions": ["A01"], "seconds": 3, "camera": "Fixed camera", "intent": "Show the authored action"}
        with (patch.object(draft, "_ask", return_value={"shots": [shot]}) as direction,
              patch.object(draft, "_select_cast", return_value={}),
              patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_script_scene", side_effect=lambda *a, **kw: {
                  "title": "Test", "continuity": "Hall", "audio": "Quiet",
                  "description": f"Action {a[5]}", "motion_prompt": f"Motion {a[5]}", "image_prompt": "Hall"}) as script):
            draft._write_planned_board(job, bindings)
            self.assertEqual(direction.call_count, 2)
            self.assertEqual([c.kwargs["proposed_shot"]["beat"]["continued_action"] for c in script.call_args_list],
                             [False, True, False, True])
            self.assertEqual([c.kwargs["proposed_shot"]["beat"]["action_phase"] for c in script.call_args_list],
                             ["prepare", "complete", "prepare", "complete"])
        draft._stamp_storyboard(job)
        draft._save(job)
        old_sha = job["storyboard_sha"]
        with (patch.object(draft.model_hub, "draft_routes", return_value=(7, bindings)),
              patch.object(draft_motion, "bind", return_value=profile),
              patch.object(draft_motion, "require_resolved_ledger"),
              patch.object(draft_motion, "prepare", return_value=(None, None, None, draft_motion.workflow_sha())),
              patch.object(draft_motion, "run_shot") as dispatch, patch.object(draft, "_image"),
              patch.object(draft, "_release_idle_image"), patch.object(draft, "_dispatch"),
              patch.object(draft, "_render", return_value="verified-fixture"),
              patch.object(draft, "_measured", return_value=nullcontext())):
            revised = draft.act(self.ident, "storyboard-edit", {
                "sha256": old_sha, "index": 0, "description": "Cửa bắt đầu mở",
                "image_prompt": "A door starting to open", "motion_prompt": "The door swings slowly"})
            self.assertEqual(revised["duration_plan"], job["duration_plan"])
            with self.assertRaises(ValueError):
                draft.act(self.ident, "storyboard-approve", {"sha256": old_sha})
            draft.act(self.ident, "storyboard-approve", {"sha256": revised["storyboard_sha"]})
            draft._work(draft._read(self.ident), nullcontext())
        self.assertEqual([call.args[0]["frames"] for call in dispatch.call_args_list], [36]*4)
        self.assertEqual(dispatch.call_args_list[0].args[0]["motion_prompt"], "The door swings slowly")
        self.assertEqual(draft._read(self.ident)["status"], "REVIEW")

    def test_authored_nine_shots_rebuilds_only_contaminated_legacy_scene_and_resumes(self):
        script = ("Video 15 giây\n\n"
                  "Cảnh 1 (0–5 giây): Mèo bước tới hộp. Camera tiến nhẹ.\n\n"
                  "Cảnh 2 (5–10 giây): Mèo chạm hộp. Hộp rung nhẹ. Camera trung cảnh.\n\n"
                  "Cảnh 3 (10–15 giây): Quả bóng vàng lăn ra khỏi hộp. "
                  "Mèo giật mình lùi lại, sau đó bước tới chạm nhẹ quả bóng. "
                  "Camera giữ ổn định, phong cách 3D.\n\nKhông lời thoại, không watermark.")
        job = {"id": self.ident, "status": "FAILED", "brief": {"idea": script, "mode": "motion",
               "seconds": None, "duration_mode": "auto", "ratio": "16:9"}, "storyboard_version": 1,
               "studio_plan": {"film.storyboard": "pinned"}}
        plan = draft._duration_plan(job, {})
        job["brief"].update(seconds=15, scene_count=9)
        job["duration_plan"] = plan
        original = [{"title": "Miu", "continuity": "A cat and a box", "description": f"Shot {i}",
                     "motion_prompt": f"Motion {i}", "image_prompt": "A cat and a box", "audio": "Quiet"}
                    for i in range(9)]
        job["storyboard_checkpoint"] = {"cast": {}, "shots": original[:7]}
        draft._save(job)
        bindings = {"general.text": {}, "film.storyboard": {}, "image.generate": {}}
        with patch.object(draft, "_script_scene", side_effect=[dict(original[6]),
                {**original[7], "description": original[6]["description"]},
                {**original[7], "motion_prompt": original[6]["motion_prompt"]},
                {**original[7], "motion_prompt": original[6]["motion_prompt"]}]) as write:
            with self.assertRaisesRegex(ValueError, "cảnh 3, shot 2"):
                draft._write_planned_board(draft._read(self.ident), bindings)
        saved = draft._read(self.ident)
        self.assertNotIn("board", saved)
        self.assertEqual(saved["studio_plan"], job["studio_plan"])
        self.assertEqual(saved["storyboard_checkpoint"]["shots"], original[:7])
        self.assertEqual([row["duplicates"] for row in saved["storyboard_rejections"]],
                         [{"description": 1}, {"motion_prompt": 1}, {"motion_prompt": 1}])
        self.assertEqual(saved["storyboard_rejections"][1]["response"]["motion_prompt"], "Motion 6")
        self.assertEqual([call.args[5] for call in write.call_args_list], [6, 7, 7, 7])
        with patch.object(draft, "_script_scene", side_effect=[dict(row) for row in original[7:]]) as write:
            draft._write_planned_board(saved, bindings)
        contexts = [call.kwargs["proposed_shot"] for call in write.call_args_list]
        self.assertEqual([call.args[5] for call in write.call_args_list], [7, 8])
        self.assertEqual([ctx["beat"]["assigned_text"] for ctx in contexts],
                         ["Mèo giật mình lùi lại", "bước tới chạm nhẹ quả bóng."])
        self.assertEqual(contexts[0]["camera"], ["Camera giữ ổn định"])
        self.assertIn("phong cách 3D.", contexts[0]["script_context"])
        self.assertIn("Không lời thoại", contexts[0]["script_context"])
        self.assertEqual([x["description"] for x in draft._read(self.ident)["board"]["scenes"]],
                         [x["description"] for x in original])
        fewer = script_analysis.shot_beat(["Mèo bước tới hộp."], 2, 3, 40, 40, None)
        self.assertTrue(fewer["continued_action"])
        self.assertEqual(fewer["assigned_text"], "Mèo bước tới hộp.")
        complete = draft._read(self.ident)
        draft._stamp_storyboard(complete)
        complete["approved_storyboard_sha"] = complete["storyboard_sha"]
        draft._save(complete)
        with self.assertRaisesRegex(ValueError, "đã hoàn chỉnh"):
            draft._write_planned_board(draft._read(self.ident), bindings)
        self.assertEqual(draft._read(self.ident), complete)

    def test_authored_planner_refuses_duplicate_shot_content(self):
        job = {"id": self.ident, "status": "RUNNING", "brief": {"idea": "Video 6 giây\nCảnh 1 (6 giây): Miu nhảy qua cửa.",
               "mode": "motion", "seconds": None, "duration_mode": "auto"}}
        bindings = {"general.text": {}, "film.storyboard": {}, "image.generate": {}}
        output = {"title": "Miu", "continuity": "Miu at the door", "description": "Miu nhảy",
                  "motion_prompt": "Miu jumps", "image_prompt": "Cat", "audio": "Quiet"}
        with (patch.object(draft, "_select_cast", return_value={}),
              patch.object(draft, "_script_scene", side_effect=lambda *a, **k: dict(output)) as write):
            with self.assertRaisesRegex(ValueError, "cảnh 1, shot 2 sau 3 lần thử"):
                draft._write_planned_board(job, bindings)
        self.assertEqual([call.args[5] for call in write.call_args_list], [0, 1, 1, 1])
        self.assertEqual(write.call_args.kwargs["proposed_shot"]["rejected_duplicate_fields"],
                         ["description", "motion_prompt"])
        self.assertEqual(write.call_args.kwargs["proposed_shot"]["already_covered"], [
            {"description": output["description"], "motion_prompt": output["motion_prompt"]}])
        self.assertEqual(write.call_args.kwargs["proposed_shot"]["previous_candidate"],
                         {"description": output["description"], "motion_prompt": output["motion_prompt"]})
        saved = draft._read(self.ident)
        self.assertNotIn("board", saved)
        self.assertEqual(saved["storyboard_checkpoint"]["shots"], [output])
        with (patch.object(draft, "_select_cast") as cast,
              patch.object(draft, "_script_scene", side_effect=[
                  dict(output),
                  {**output, "description": "Miu qua mép cửa", "motion_prompt": "Miu crosses the threshold"},
                  {**output, "description": "Miu tiếp đất", "motion_prompt": "Miu lands"},
              ]) as resume):
            draft._write_planned_board(saved, bindings)
        cast.assert_not_called()
        self.assertEqual([call.args[5] for call in resume.call_args_list], [1, 1, 2])
        saved = draft._read(self.ident)
        self.assertNotIn("storyboard_checkpoint", saved)
        self.assertEqual([shot["motion_prompt"] for shot in saved["board"]["scenes"]],
                         ["Miu jumps", "Miu crosses the threshold", "Miu lands"])

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
        self.assertFalse(script_analysis.needs_scene_analysis("Một chú mèo đi tìm bạn."))
        text = "Cảnh 1 — Miu nhìn ra cửa sổ 🐱\nMiu: Chào bạn!\n\nCảnh 2 — Miu chạy ra vườn."
        self.assertTrue(script_analysis.needs_scene_analysis(text))
        ranges = script_analysis.script_ranges(text, 2, 12)
        self.assertEqual("".join(text[start:end] for start,end in ranges), text)
        self.assertTrue(text[ranges[1][0]:].startswith("Cảnh 2"))
        with self.assertRaisesRegex(ValueError, "3 cảnh"):
            script_analysis.script_ranges(text+"\nCảnh 3 — Trời tối.", 2, 12)
        with self.assertRaisesRegex(ValueError, "Thời lượng"):
            script_analysis.script_ranges(text+"\nMiu: "+"chào "*50, 2, 6)

    def test_long_script_analysis_uses_bounded_excerpts_before_storyboard(self):
        source = "Miu nhìn ra cửa sổ. 🐱\n" * 140
        job = {"id": self.ident, "status": "RUNNING", "brief": {
            **self.brief, "duration_mode": "manual", "idea": source}}
        provider = {"provider": "ollama", "model": "fixture"}
        excerpts = []

        def respond(profile, instructions, data, schema, comfy, **kwargs):
            if "excerpt" in data:
                excerpts.append(data["excerpt"])
                self.assertLessEqual(len(data["excerpt"]), 900)
                return {"facts": "Miu chờ bên cửa sổ."}
            self.assertLess(len(str(data)), len(source))
            return {"title": "Miu", "continuity": "Orange cat", "description": "Miu đợi",
                    "image_prompt": "Orange cat by a window", "audio": "Yên tĩnh"}

        with (patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", side_effect=respond)):
            result = draft._script_scene(job, provider, None, source, "", 0,
                proposed_shot={"action": "Miu đợi", "reason": "Mở đầu", "timeline_seconds": 3})
        self.assertEqual("".join(excerpts), source)
        self.assertEqual(result["title"], "Miu")

    def test_long_vietnamese_script_http_sqlite_roundtrip_and_limit(self):
        client = owner_http_fixture.OwnerHttpFixture()
        client.setUp()
        self.addCleanup(client.doCleanups)
        client.server.allow_external_actions = True
        client.login()
        prefix = "Cảnh 1 — Miu nhìn ra cửa sổ.\nMiu: Chào bạn!\n"
        suffix = "\n\nCảnh 2 — Miu chạy ra vườn.\n"
        source = prefix + "🐱" * (20_000 - len(prefix) - len(suffix)) + suffix
        body = {**self.brief, "id":self.ident, "idea":source,
                "mode": "still", "duration_mode": "manual", "scene_count": None}
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

    def test_http_rejects_retired_submission_and_scene_edit_contracts(self):
        client = owner_http_fixture.OwnerHttpFixture()
        client.setUp()
        self.addCleanup(client.doCleanups)
        client.server.allow_external_actions = True
        client.login()
        route = "/api/film/drafts/start"
        old = {**self.brief, "id": self.ident, "mode": "still"}
        current = {**old, "duration_mode": "manual", "scene_count": None}
        with patch.object(draft, "submit") as submit:
            for invalid in (old, {**old, "motion_approved": True},
                            {**current, "duration_mode": None},
                            {**current, "scene_count": 2},
                            {**current, "motion_approved": True}):
                with self.subTest(fields=invalid):
                    self.assertEqual(client.req("POST", route, invalid)[0], 400)
            submit.assert_not_called()
        with patch.object(draft, "act") as act:
            self.assertEqual(client.req("POST", f"/api/film/drafts/{self.ident}/edit",
                             {"index": 0, "description": "New scene", "image_prompt": "Cat"})[0], 400)
            act.assert_not_called()

    def test_current_30_second_plan_does_not_request_legacy_duration_weight(self):
        profile = {"provider": "ollama", "model": "fixture"}
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion",
                "seconds": 30, "scene_count": 15, "duration_mode": "manual"}}
        proposed = {"action": "Cat walks", "reason": "Opening", "timeline_seconds": 2}
        with (patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_ask", return_value={}) as ask):
            draft._script_scene(job, profile, None, "Cat walks", "", 0, proposed_shot=proposed)
        _, instructions, context, schema, _ = ask.call_args.args
        self.assertNotIn("duration_weight", schema["properties"])
        self.assertNotIn("duration_weight", instructions)
        self.assertEqual(context["seconds"], 2)

    def test_submission_validation_and_idempotence(self):
        with self.assertRaises(ValueError):
            draft.submit({"id": self.ident, **self.submission, "ratio": "4:3"})
        with self.assertRaisesRegex(ValueError, "current Studio brief"):
            draft.submit({"id": self.ident, **self.brief})
        self.assertEqual(draft.list_drafts(), [])
        stored = {key: value for key, value in self.submission.items() if key != "mode"}
        draft._save({"id": self.ident, "brief": stored, "status": "RUNNING"})
        self.assertEqual(draft.submit({"id": self.ident, **self.submission})["id"], self.ident)
        with self.assertRaises(ValueError):
            draft.submit({"id": self.ident, **self.submission, "idea": "Khác"})
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
        body = {**self.brief, "id": self.ident, "seconds": 4, "mode": "motion",
                "duration_mode": "manual", "scene_count": None}
        route = "/api/film/drafts/start"
        self.assertEqual(client.req("POST", route, {**body, "seconds": 3})[0], 400)
        profile = {"id": "selected_by_registry", "provider": "comfyui", "model": ltx.CHECKPOINT, "enabled": True,
                   "motion_encoder": str(self.root / ltx.ENCODER), "base_url": "http://127.0.0.1:8188"}
        image_profile = flux_profile()
        self.seed_registry(image_profile, profile)
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
            job["brief"]["scene_count"] = 2

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
                self.registry_change("SAVE_MODEL_PROFILE", profile=writer)
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
                    self.registry_change("SAVE_MODEL_PROFILE", profile=image_profile if changed["id"] == image_profile["id"] else profile)
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
            self.registry_change("SAVE_MODEL_PROFILE", profile=profile)
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
                self.registry_change("DELETE_MODEL_PROFILE", profile_id=replacement["id"])
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

    def test_public_view_uses_backend_limits_without_mutating_checkpoint(self):
        from agentforge.features.film_studio import draft_timeline

        job = {"id": self.ident, "status": "STORYBOARD_REVIEW", "storyboard_version": 1,
               "brief": {**self.brief, "mode": "motion", "seconds": 24, "duration_mode": "auto"},
               "motion_plan": {"output": {"fps": 24, "max_frames": 240, "resolution": [1280, 720]}},
               "board": {"scenes": [{"frames": 145}, {"frames": 240, "motion_job": "existing"},
                                    {"frames": 48}]},
               "production_plan": {"method": "cloud"}}
        before = json.dumps(job, sort_keys=True)
        view = draft.public_view(job)
        self.assertEqual(view["editor_constraints"], {
            "duration": {"min": 4, "max": 60}, "layout_editable": True,
            "duration_editable": True, "min_scenes": 3, "max_scenes": 16})
        self.assertEqual(view["cloud_seconds_remaining"], 14)
        self.assertEqual(json.dumps(job, sort_keys=True), before)
        self.assertNotIn("editor_constraints", job)
        for modified in ({**job, "status": "RUNNING"},
                         {**job, "storyboard_version": draft_timeline.MAX_VERSIONS},
                         {**job, "duration_plan": {"content_scene_count": 2}}):
            self.assertFalse(draft.public_view(modified)["editor_constraints"]["layout_editable"])
        legacy = {**job, "brief": {**self.brief, "mode": "motion", "seconds": 15}}
        limits = draft.public_view(legacy)["editor_constraints"]
        self.assertEqual((limits["min_scenes"], limits["max_scenes"]), (8, 9))
        self.assertFalse(limits["duration_editable"])
        self.assertEqual(draft.public_view({"id": self.ident, "deleted": True}),
                         {"id": self.ident, "deleted": True})

    def test_historical_30_second_timeline_preserves_frame_budget(self):
        frames = draft.draft_timeline.timeline(30, 16, [1+i%3 for i in range(16)])
        self.assertEqual(sum(frames), 720)
        self.assertTrue(all(40 <= frame <= 49 for frame in frames))
        self.assertGreater(len(set(frames)), 1)
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
            job = draft.submit({"id": self.ident, **self.submission})
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

    def test_confirmed_motion_retry_replaces_only_the_failed_attempt(self):
        runner = draft_motion
        old_id, new_id = "a"*32, "b"*32
        scene = {"motion_job": old_id, "job_id": "image", "asset": "image-sha", "description": "A cat"}
        row = {"state": "FAILED", "film_slug": "film", "shot_id": "sh-00003", "plan_sha": "plan"}
        prepared = ("film", "plan", self.root/"graph.json", "sha")
        with (patch.object(runner.motion_verify, "_job", return_value=row),
              patch.object(runner, "_provider") as provider,
              patch.object(runner.motion_verify, "inspect_receipt", return_value={"clip_sha256": "clip"}),
              patch.object(runner.motion_comfy, "submit_shot",
                           side_effect=lambda **args: args["on_reserved"](new_id)) as submit):
            runner.run_shot(scene, 2, prepared, {"motion_encoder": "encoder"}, lambda: None,
                            lambda: False, retry_motion_job=old_id)
            self.assertIs(submit.call_args.kwargs["confirm_new_attempt"], True)
            self.assertEqual(submit.call_args.kwargs["image_job"], "image")
            self.assertEqual(scene["motion_job"], new_id)
            self.assertEqual(scene["motion_sha"], "clip")
            provider.assert_called_once()
            row["state"] = "SUBMITTING"
            with self.assertRaises(ValueError):
                runner.retryable_motion_job(old_id)

    def test_resume_requires_confirmation_bound_to_the_failed_motion_checkpoint(self):
        attempt = "a"*32
        draft._save({"id": self.ident, "status": "FAILED", "stage": "MOTION",
                     "brief": self.brief, "failed_scene": 2, "board": {"scenes": [
                         {"motion_job": "b"*32, "motion_sha": "verified"}, {"motion_job": attempt}]}})
        with (patch.object(draft, "_studio_bindings"),
              patch.object(draft, "_start", side_effect=lambda job, slot, _: slot.__exit__(None, None, None)) as start,
              patch.object(draft_motion, "retryable_motion_job") as eligible):
            with self.assertRaises(ValueError):
                draft.act(self.ident, "resume", {"retry_motion_job": "b"*32})
            start.assert_not_called()
            eligible.assert_not_called()
            draft.act(self.ident, "resume", {"retry_motion_job": attempt})
            eligible.assert_called_once_with(attempt)
            self.assertEqual(start.call_args.args[2], attempt)

    def test_motion_interrupt_reports_resource_reason_and_targets_only_its_prompt(self):
        runner = draft_motion
        provider = str(uuid4())
        with (patch.object(runner.motion_verify, "_job", return_value={"provider_id": provider}),
              patch.object(runner.motion_comfy, "job_status", side_effect=[
                  {"status": "PROVIDER_QUEUED_OR_UNKNOWN"},
                  {"status": "PROVIDER_QUEUED_OR_UNKNOWN"}, {"status": "PROVIDER_FAILED"}]),
              patch.object(runner.draft_resources, "memory_snapshot", return_value={
                  "ram_available": 5*1024**3, "commit_used": 38*1024**3, "commit_limit": 42*1024**3}),
              patch.object(runner.comfy_service.comfyui, "request_image_bytes", side_effect=[
                  json.dumps({"queue_pending": [], "queue_running": [[0, str(uuid4())]]}).encode(),
                  json.dumps({"queue_pending": [], "queue_running": [[0, provider]]}).encode()]),
              patch.object(runner.http.client, "HTTPConnection") as transport,
              patch.object(runner.time, "sleep")):
            transport.return_value.getresponse.return_value.status = 200
            with self.assertRaisesRegex(ValueError, "commit headroom"):
                runner._provider("b"*32, lambda: False)
            transport.return_value.request.assert_called_once_with(
                "POST", "/interrupt", body=json.dumps({"prompt_id": provider}),
                headers={"Content-Type": "application/json"})

    def test_motion_interrupt_transport_failure_requires_reconciliation(self):
        runner = draft_motion
        provider = str(uuid4())
        queue = json.dumps({"queue_pending": [], "queue_running": [[0, provider]]}).encode()
        with (patch.object(runner.motion_verify, "_job", return_value={"provider_id": provider}),
              patch.object(runner.motion_comfy, "job_status", return_value={"status": "PROVIDER_QUEUED_OR_UNKNOWN"}),
              patch.object(runner.comfy_service.comfyui, "request_image_bytes", return_value=queue),
              patch.object(runner.http.client, "HTTPConnection") as transport):
            transport.return_value.getresponse.side_effect = TimeoutError()
            with self.assertRaises(runner.NeedsReconciliation):
                runner._provider("b"*32, lambda: True)
            transport.return_value.request.assert_called_once()

    def test_storyboard_rejects_unknown_cast_and_distributes_exact_duration(self):
        with self.assertRaisesRegex(ValueError, "unknown character"):
            draft._story(self.board(), 2, 7, {})
        result = draft._story(self.board(), 2, 7, {"cat": {}})
        self.assertEqual([scene["seconds"] for scene in result["scenes"]], [4, 3])

    def test_incomplete_legacy_draft_cannot_run_retired_planner(self):
        job = {"id": self.ident, "status": "RUNNING", "stage": "PLANNING",
               "storyboard_version": 1, "brief": {**self.brief, "mode": "motion",
                                                    "seconds": 15, "scene_count": 8}}
        draft._save(job)
        with (patch.object(draft, "_studio_bindings") as bindings,
              patch.object(draft, "_ask") as ask, patch.object(draft, "_dispatch")):
            draft._work(job, nullcontext())
            saved = draft._read(self.ident)
            self.assertEqual(saved["status"], "FAILED")
            self.assertIn("planner cũ", saved["error"])
            self.assertNotIn("board", saved)
            self.assertEqual(saved["brief"], job["brief"])
            with self.assertRaisesRegex(ValueError, "planner cũ"):
                draft.act(self.ident, "resume", {})
            with self.assertRaisesRegex(ValueError, "planner cũ"):
                draft._write_board(saved, {})
            bindings.assert_not_called()
            ask.assert_not_called()

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
            self.assertEqual(job["error"], "Image scene result: COMFYUI_STOPPED")
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

    def test_draft_store_read_only_and_atomic_queue_operations(self):
        from agentforge.features.film_studio import draft_store as store

        db = self.root / "storage.sqlite3"
        self.assertEqual(store.recent(db), [])
        self.assertFalse(store.pending(db))
        self.assertIsNone(store.next_queued(db))
        self.assertFalse(store.cancellation(db, self.ident))
        with self.assertRaises(store.DraftNotFound):
            store.read(db, self.ident)
        self.assertFalse(db.exists())
        job = {"id": self.ident, "brief": self.brief, "status": "QUEUED"}
        with store.connect(db, True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.assertIsNone(store.insert_queued(conn, job, 1))
            self.assertEqual(store.insert_queued(conn, job, 1), job)
        self.assertEqual(store.next_queued(db), job)
        self.assertTrue(store.pending(db))
        another = {**job, "id": "b"*32}
        with self.assertRaisesRegex(ValueError, "queue"):
            with store.connect(db, True) as conn:
                conn.execute("BEGIN IMMEDIATE")
                store.insert_queued(conn, another, 1)
        self.assertEqual(store.recent(db), [job])
        store.save(db, {**job, "status": "WAITING_RESOURCES"}, updated_at="2026-11-26T00:00:00Z")
        self.assertIsNone(store.next_queued(db))
        self.assertTrue(store.other_waiting(db, another["id"]))
        self.assertFalse(store.other_waiting(db, self.ident))
        self.assertTrue(store.cancellation(db, self.ident, mark=True))
        with self.assertRaises(RuntimeError):
            with store.connect(db, True) as conn:
                conn.execute("BEGIN IMMEDIATE")
                store.delete_record(conn, self.ident)
                raise RuntimeError("rollback fixture")
        self.assertEqual(store.read(db, self.ident)["status"], "WAITING_RESOURCES")
        self.assertTrue(store.cancellation(db, self.ident))
        with store.connect(db, True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            store.delete_record(conn, self.ident)
        self.assertFalse(store.pending(db))
        self.assertFalse(store.cancellation(db, self.ident))

    def test_queue_limit_idempotence_and_queued_cancel(self):
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {})), patch.object(draft.render, "_ffmpeg"),
              patch.object(draft, "_queue_limit", return_value=1), patch.object(draft, "_dispatch")):
            submitted = draft.submit({"id": self.ident, **self.submission})
            self.assertEqual(submitted["status"], "QUEUED")
            self.assertEqual(submitted["created_at"], submitted["updated_at"])
            self.assertEqual(draft.submit({"id": self.ident, **self.submission})["id"], self.ident)
            with self.assertRaisesRegex(ValueError, "queue"):
                draft.submit({"id": "b" * 32, **self.submission})
            cancelled = draft.act(self.ident, "cancel", {})
            self.assertEqual(cancelled["status"], "CANCELLED")
            self.assertEqual(draft._read(self.ident)["created_at"], submitted["created_at"])
            self.assertEqual(draft.submit({"id": "b" * 32, **self.submission})["status"], "QUEUED")

    def test_worker_launch_failure_restores_prior_checkpoint_and_releases_slot(self):
        job = {"id": self.ident, "brief": self.brief, "status": "QUEUED",
               "stage": "MOTION", "board": self.board(), "attempt_started_at": "prior-start",
               "attempt_finished_at": "prior-finish", "error_code": "prior-error"}
        draft._save(job)
        prior = draft._read(self.ident)
        with (patch.object(draft, "ACTIVE", None),
              patch.object(draft.threading, "Thread", side_effect=RuntimeError("secret-provider-payload")),
              self.assertLogs(draft.LOG, level="ERROR") as logs):
            with self.assertRaisesRegex(RuntimeError, "^STUDIO_WORKER_START_FAILED$"):
                draft._dispatch()
            self.assertIsNone(draft.ACTIVE)
            with draft._worker_slot():
                pass
        restored = draft._read(self.ident)
        restored.pop("updated_at")
        prior.pop("updated_at")
        self.assertEqual(restored, prior)
        self.assertNotIn("secret-provider-payload", str(logs.output))

    def test_cancel_checks_production_identity_not_any_active_worker(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING",
               "stage": "MOTION", "storyboard_version": 1}
        draft._save(job)
        with (patch.object(draft, "ACTIVE", "b"*32), patch.object(draft, "_dispatch") as dispatch):
            with self.assertRaisesRegex(ValueError, "đối soát"):
                draft.act(self.ident, "cancel", {})
            self.assertFalse(draft._cancellation(self.ident))
            self.assertEqual(draft._read(self.ident)["status"], "RUNNING")
            draft._save({**job, "stage": "STORYBOARD"})
            result = draft.act(self.ident, "cancel", {})
            self.assertEqual(result["status"], "CANCELLED")
            self.assertEqual(draft._read(self.ident)["status"], "CANCELLED")
            self.assertTrue(draft._cancellation(self.ident))
            dispatch.assert_called_once()

    def test_lifecycle_keeps_reconciliation_visible_on_cancellation(self):
        from agentforge.features.film_studio import draft_lifecycle

        job = {"status": "NEEDS_RECONCILIATION", "error": "Unknown remote outcome",
               "attempt_started_at": "start", "activity": {"scene": 2}}
        draft_lifecycle.finish_attempt(job, "finish", cancelled=True)
        self.assertEqual(job["status"], "NEEDS_RECONCILIATION")
        self.assertEqual(job["error"], "Unknown remote outcome")
        self.assertEqual(job["attempt_finished_at"], "finish")
        self.assertNotIn("activity", job)

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

    def test_canonical_storyboard_layout_preserves_still_and_motion_budgets(self):
        timeline = draft.draft_timeline
        still = {"brief": {"seconds": 7}}
        self.assertEqual(timeline.job_fps(still), 24)
        self.assertEqual(timeline.storyboard_layout(still, 2), [96, 72])

        moving = {"brief": {"mode": "motion", "seconds": 4, "duration_mode": "manual"},
                  "motion_plan": {"output": {"fps": 25, "max_frames": 60, "resolution": [512, 288]}}}
        self.assertEqual(timeline.job_fps(moving), 25)
        self.assertEqual(timeline.storyboard_layout(moving, 2), [50, 50])
        moving["duration_plan"] = {"content_scene_count": 1, "shots": [
            {"script_shot_frames": 60}, {"script_shot_frames": 40}]}
        self.assertEqual(timeline.storyboard_layout(moving, 2), [60, 40])
        moving["duration_plan"]["shots"][0]["script_shot_frames"] = 61
        with self.assertRaises(ValueError):
            timeline.storyboard_layout(moving, 2)

    def test_cleanup_failure_preserves_cancelled_checkpoint_and_dispatch(self):
        job = {"id": self.ident, "brief": self.brief, "status": "RUNNING", "stage": "IMAGES",
               "board": draft._story(self.board(), 2, 6, {"cat": {}}), "cast": {},
               "attempt_started_at": "2026-11-26T00:00:00Z"}
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
              patch.object(draft, "_dispatch") as dispatch,
              patch.object(draft, "_release_idle_image", side_effect=RuntimeError("secret-provider-payload")) as release,
              self.assertLogs(draft.LOG, level="WARNING") as logs):
            draft._work(job, nullcontext())
        image.assert_called_once()
        render.assert_not_called()
        release.assert_called_once_with(profile)
        dispatch.assert_called_once()
        restored = draft._read(self.ident)
        self.assertEqual(restored["status"], "CANCELLED")
        self.assertEqual(restored["board"]["scenes"][0]["asset"], "committed")
        self.assertTrue(restored["attempt_finished_at"])
        self.assertNotIn("activity", restored)
        self.assertIsNone(draft.ACTIVE)
        self.assertIn("STUDIO_IMAGE_CLEANUP_FAILED", str(logs.output))
        self.assertNotIn("secret-provider-payload", str(logs.output))
        self.assertNotIn("secret-provider-payload", str(restored))

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
                with self.assertRaisesRegex(ValueError, "Draft cannot be resumed"):
                    draft.act(self.ident, "edit", {
                        "index": 1, "description": "Sửa", "image_prompt": "New scene"})
                self.assertEqual(draft._read(self.ident)["board"], job["board"])
                self.assertEqual(draft._read(self.ident)["video_sha"], job["video_sha"])
                result = draft.act(self.ident, "approve", {"sha256": job["video_sha"]})
                self.assertEqual(result["status"], "APPROVED")
