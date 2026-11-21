"""Draft schema, checkpoint lifecycle, and real local MP4 quality gate."""
import tempfile
import io
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack, nullcontext
from types import SimpleNamespace
from uuid import uuid4

from agentforge.features.film_studio import draft_pipeline as draft
from tests import owner_http_fixture


class DraftTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in (("DB", self.root / "drafts.sqlite3"), ("WORKSPACE_DIR", self.root)):
            override = patch.object(draft, name, value)
            override.start()
            self.addCleanup(override.stop)
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
        with (patch.object(draft.model_hub, "draft_routes"), patch.object(draft.render, "_ffmpeg"),
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
        motion = draft.draft_motion.motion_comfy
        runner = draft.draft_motion
        ltx = runner.motion_ltx
        client = owner_http_fixture.OwnerHttpFixture()
        client.setUp()
        self.addCleanup(client.doCleanups)
        client.server.allow_external_actions = True
        client.login()
        body = {**self.brief, "id": self.ident, "seconds": 4, "mode": "motion"}
        route = "/api/film/drafts/start"
        self.assertEqual(client.req("POST", route, {**body, "seconds": 6})[0], 400)
        profile = {"id": "selected_by_registry", "provider": "comfyui", "model": ltx.CHECKPOINT,
                   "motion_encoder": str(self.root / ltx.ENCODER), "base_url": "http://127.0.0.1:8188"}
        bindings = {"film.motion": profile, "image.generate": {
            "provider": "comfyui", "model": "fixture.gguf", "flux": {"max_resolution": 768}}}
        output = self.root / "output"
        output.mkdir()
        asset = b"FLUX fixture"
        calls = []
        latest = {}

        def provider(path, *, body=None, timeout=6):
            if path == "/prompt":
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
            return {path.split("/")[-1]: latest[path.split("/")[-1]]}

        def image(*args, **kwargs):
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

        def storyboard(job, _):
            job.update(board=draft._story(self.board(), 2, 4, {"cat": {}}),
                       cast={"cat": {"name": "Miu", "appearance": "orange cat"}})

        patches = (patch.object(draft.model_hub, "draft_routes", return_value=(8, bindings)),
              patch.object(draft, "_dispatch"), patch.object(draft, "_write_board", side_effect=storyboard),
              patch.object(draft, "_measured", return_value=nullcontext()),
              patch.object(draft, "_release_idle_comfy"),
              patch.object(draft.flux_runtime, "generate", side_effect=image),
              patch.object(draft.visual_jobs, "open_image_for_job",
                           side_effect=lambda _: nullcontext((io.BytesIO(asset), draft._sha(asset)))),
              patch.object(draft.render, "_ffmpeg", return_value="ffmpeg"),
              patch.object(draft.render, "_run_process", side_effect=ffmpeg),
              patch.object(runner.shutil, "which", return_value="fixture"),
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
            approval = route.removesuffix("/start") + f"/{self.ident}/storyboard-approve"
            self.assertEqual(client.req("POST", approval, {"sha256": "stale"})[0], 400)
            self.assertEqual(client.req("POST", approval, {"sha256": job["storyboard_sha"]})[0], 200)
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
              patch.object(draft.draft_motion, "require_resolved_ledger")):
            job = draft.submit({"id": self.ident, **self.brief})
            draft._work(job, nullcontext())
            self.assertEqual(draft._read(self.ident)["status"], "STORYBOARD_REVIEW")
            image.assert_not_called()

    def test_motion_failure_does_not_render_or_dispatch_another_shot(self):
        job = {"id": self.ident, "brief": {**self.brief, "mode": "motion", "seconds": 4},
               "status": "RUNNING", "motion_revision": 8,
               "board": draft._story(self.board(), 2, 4, {"cat": {}}), "cast": {}}
        def fail(*args):
            args[0]["motion_job"] = "b" * 32
            args[4]()
            raise ValueError("Motion dispatch requires reconciliation")
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": {}})),
              patch.object(draft, "_image"), patch.object(draft, "_release_idle_comfy"),
              patch.object(draft.draft_motion, "binding", return_value={"provider": "comfyui", "model": "fixture"}),
              patch.object(draft.draft_motion, "require_resolved_ledger"),
              patch.object(draft.draft_motion, "prepare"), patch.object(draft, "_dispatch"),
              patch.object(draft.draft_motion, "run_shot", side_effect=fail) as run,
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
        runner = draft.draft_motion
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
        runner = draft.draft_motion
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
        profile = {"provider": "comfyui", "model": "fixture.gguf", "flux": {"max_resolution": 768}}
        def missing_output(*args, **kwargs):
            self.assertEqual(draft._read(self.ident)["activity"], {
                "operation": "image", "provider": "comfyui", "model": "fixture.gguf", "scene": 2,
            })
            return {"status": "COMFYUI_STOPPED"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": profile})),
              patch.object(draft.flux_runtime, "generate", side_effect=missing_output) as generate):
            draft._work(job, nullcontext())
            self.assertEqual(job["status"], "FAILED")
            self.assertEqual(job["error"], "ComfyUI scene result: COMFYUI_STOPPED")
            self.assertNotIn("activity", job)
            self.assertEqual(job["board"]["scenes"][1]["attempts"], 1)
            generate.assert_called_once()
        recovered = draft._read(self.ident)
        with (patch.object(draft.model_hub, "draft_routes", return_value=(8, {"image.generate": profile})),
              patch.object(draft.visual_jobs, "_row", side_effect=KeyError),
              patch.object(draft.flux_runtime, "generate", return_value={"status": "ASSET_READY"}) as generate,
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
        profile = {"flux": {"max_resolution": 768}}
        for error in ("COMFYUI_LAUNCHER_REQUIRED", "COMFYUI_ENDPOINT_MISMATCH"):
            with (self.subTest(error=error),
                  patch.object(draft.flux_runtime, "generate",
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
        with (patch.object(draft.model_hub, "draft_routes"), patch.object(draft.render, "_ffmpeg"),
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

        profile = {"base_url": "http://127.0.0.1:8188", "provider": "comfyui", "model": "fixture.gguf"}
        with (patch.object(draft.model_hub, "draft_routes", return_value=(1, {"image.generate": profile})),
              patch.object(draft.comfy_service, "require_other_queue_idle"),
              patch.object(draft.comfy_service, "require_idle_queue"),
              patch.object(draft, "_image", side_effect=complete_scene) as image,
              patch.object(draft, "_render") as render,
              patch.object(draft, "_release_idle_comfy") as release):
            draft._work(job, nullcontext())
            image.assert_called_once()
            render.assert_not_called()
            release.assert_called_once_with(profile)
        restored = draft._read(self.ident)
        self.assertEqual(restored["status"], "CANCELLED")
        self.assertEqual(restored["board"]["scenes"][0]["asset"], "committed")

    def test_comfy_offload_skipped_during_commit_pressure(self):
        with (patch.dict(self.capacity, {"commit_used": 31 << 30}),
              patch.object(draft.flux_runtime, "_json") as request):
            self.assertFalse(draft._release_idle_comfy({"base_url": "http://127.0.0.1:8188"}))
            request.assert_not_called()

    def test_ollama_500_does_not_retry(self):
        profile = {"id": "fixture", "model": "fixture", "base_url": "http://127.0.0.1:11434"}
        with (patch.object(draft.runtime, "_installed_local_model", return_value=True),
              patch.object(draft.runtime, "_http_json",
                           side_effect=draft.runtime.LocalProviderHTTPError(500)) as request,
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
