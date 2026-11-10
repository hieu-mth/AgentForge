"""Wave 9 Film Production: signed shot continuity, offline TTS, FFmpeg and QA.

These are fixture contracts, not evidence of real ComfyUI film clips or human
continuity acceptance. No native FFmpeg/voice/model is executed in CI.
"""
import hashlib
import json
import tempfile
import unittest
import wave
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agentforge.features.film_studio import long_form, motion_comfy, motion_verify, production

RAW = b"\x00\x00\x00\x18ftypisom" + b"fixture motion content" * 150
CLIP_SHA = hashlib.sha256(RAW).hexdigest()
PLAN_SHA = "a" * 64
WORKFLOW_SHA = "b" * 64
PROMPT_SHA = "c" * 64
REFERENCE_SHA = "f" * 64


class FilmProductionWave9Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.films = self.root / "workspace" / "films"
        self.db = self.root / "data" / "motion.sqlite3"
        self.plan = None
        self.spec = None

    def bootstrap(self, size=3, duplicate_media=False):
        self.plan = long_form.build_plan(
            title="Original Fox Film", genre="fantasy", style="noir",
            characters=[{"id": "fox", "name": "The Fox",
                         "visual_bible": "Red fox, blue scarf, left ear mark",
                         "voice_notes": "Calm Vietnamese narration"}],
            chapters=[{"id": "forest", "title": "The search",
                       "synopsis": "The same fox explores an ancient forest.",
                       "duration_seconds": 4 * size, "character_ids": ["fox"]}],
            shot_seconds=4)
        long_form.save_plan(self.films, "fox-film", self.plan)
        entries = []
        for index, shot in enumerate(self.plan["shots"]):
            job = uuid4().hex
            name = shot["shot_id"]
            folder = self.films / "fox-film" / "motion_clips" / job
            folder.mkdir(parents=True)
            payload = RAW + (b"same" if duplicate_media else index.to_bytes(4, "big"))
            clip_sha = hashlib.sha256(payload).hexdigest()
            (folder / "clip.mp4").write_bytes(payload)
            provider = str(uuid4())
            body = {
                "format": "agentforge.film.motion.receipt.v1",
                "job_id": job, "film_slug": "fox-film", "shot_id": name,
                "plan_sha": self.plan["plan_sha256"],
                "workflow_sha": WORKFLOW_SHA, "prompt_sha": PROMPT_SHA,
                "seed": index + 1, "provider_id": provider,
                "model_id": motion_verify.MODEL_ID,
                "state": motion_verify.TECHNICAL,
                "clip_sha256": clip_sha, "bytes": len(payload),
                "technical": {"codec": "h264", "width": 640, "height": 352,
                              "fps": 12, "frames_decoded": 49,
                              "duration_seconds": 4.083},
                "imported_at": motion_comfy._now(),
                "wall_seconds_from_submission_to_import": 10.0,
                "owner_reported_peak_vram_gib": None,
                "peak_vram_automatically_measured": False,
                "motion_quality_verified": False, "owner_watched": False,
                "video_accepted": False, "youtube_uploaded": False,
            }
            receipt_sha = motion_verify._digest(body)
            with (folder / "receipt.json").open("x", encoding="utf-8") as f:
                json.dump({**body, "receipt_sha256": receipt_sha}, f)
            with closing(motion_comfy._db(self.db, write=True)) as conn:
                conn.execute("""INSERT INTO motion_jobs(job_id, film_slug, shot_id, plan_sha,
                    workflow_sha, prompt_sha, seed, provider_id, state, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,'COMPLETE_UNVERIFIED',?,?)""",
                    (job, "fox-film", name, self.plan["plan_sha256"], WORKFLOW_SHA,
                     PROMPT_SHA, index + 1, provider, motion_comfy._now(),
                     motion_comfy._now()))
                conn.commit()
            entries.append({
                "shot_id": name, "job_id": job, "clip_sha256": clip_sha,
                "receipt_sha256": receipt_sha, "character_ids": ["fox"],
                "location_id": "forest", "costume_id": "blue-scarf",
                "prop_ids": ["small-map"], "reference_sha256": REFERENCE_SHA,
                "action_camera": f"The fox walks slowly, camera tracks shot {index}.",
                "caption": f"Đây là cảnh thứ {index + 1} của câu chuyện gốc.",
                "change_note": "",
            })
        self.spec = {
            "film_slug": "fox-film", "episode_id": "episode-one",
            "plan_sha": self.plan["plan_sha256"],
            "shots": entries, "source_episode_id": None,
            "source_sha256": None,
        }
        return self.spec

    def propose(self):
        return production.prepare(self.spec, film_root=self.films, db_path=self.db)

    def test_three_to_five_shot_continuity_and_signed_srt(self):
        self.bootstrap(3)
        first = self.propose()
        self.assertEqual(first["shot_count"], 3)
        self.assertEqual(first["runtime_seconds"], 12.25)
        self.assertFalse(first["visual_continuity_verified"])
        doc = production.inspect("episode-one", "fox-film", film_root=self.films)
        self.assertEqual(doc["episode_sha256"], first["episode_sha256"])
        captions = production._srt(doc["shots"])
        self.assertIn("00:00:04,083", captions)
        self.assertIn("00:00:12,250", captions)
        with self.assertRaises(FileExistsError):
            self.propose()
        self.assertEqual(len(production.list_episodes(film_root=self.films)), 1)

    def test_15_and_22_shots_duration_without_looping(self):
        for count, duration in [(15, 61.25), (22, 89.833)]:
            with self.subTest(count=count):
                with tempfile.TemporaryDirectory() as td:
                    self.films = Path(td) / "workspace" / "films"
                    self.db = Path(td) / "motion.sqlite3"
                    self.bootstrap(count)
                    receipt = self.propose()
                    self.assertEqual(receipt["shot_count"], count)
                    self.assertAlmostEqual(receipt["runtime_seconds"], duration, places=3)
                    self.assertFalse(receipt["generated_new_clips"])

    def test_draft_only_from_verified_motion_and_forces_owner_notes(self):
        self.bootstrap(3)
        edited = production.draft(
            "fox-film", "draft-one", shot_count=3,
            film_root=self.films, db_path=self.db)
        self.assertEqual(edited["episode_id"], "draft-one")
        self.assertEqual(edited["shots"][0]["receipt_sha256"],
                         self.spec["shots"][0]["receipt_sha256"])
        self.assertIn("OWNER REVIEW REQUIRED:", edited["shots"][1]["caption"])
        with self.assertRaisesRegex(production.FilmProductionError, "Owner must"):
            production.prepare(edited, film_root=self.films, db_path=self.db)
        self.assertFalse((self.films / "fox-film" / "productions").exists())
        with self.assertRaises(production.FilmProductionError):
            production.draft("fox-film", "big", shot_count=4,
                             film_root=self.films, db_path=self.db)

    def test_duplicate_mp4_content_sha_is_blocked_even_when_job_ids_differ(self):
        self.bootstrap(3, duplicate_media=True)
        self.assertNotEqual(self.spec["shots"][0]["job_id"], self.spec["shots"][1]["job_id"])
        self.assertEqual(self.spec["shots"][0]["clip_sha256"], self.spec["shots"][1]["clip_sha256"])
        with self.assertRaisesRegex(production.FilmProductionError, "Duplicate motion MP4 SHA"):
            self.propose()

    def test_rejects_missing_real_clip_tamper_and_fake_success(self):
        self.bootstrap(3)
        clip = (self.films / "fox-film" / "motion_clips"
                / self.spec["shots"][1]["job_id"] / "clip.mp4")
        clip.write_bytes(b"tampered")
        with self.assertRaises(motion_verify.MotionVerificationError):
            self.propose()
        self.assertFalse((self.films / "fox-film" / "productions").exists())

    def test_unapproved_cast_change_without_continuity_note_is_blocked(self):
        self.bootstrap(3)
        self.spec["shots"][1]["costume_id"] = "red-robe"
        with self.assertRaisesRegex(production.FilmProductionError, "continuity"):
            self.propose()
        self.spec["shots"][1]["change_note"] = "Explicit costume change after the river."
        self.spec["shots"][2]["costume_id"] = "red-robe"
        self.propose()
        self.assertFalse(production.inspect(
            "episode-one", "fox-film", film_root=self.films
        )["visual_continuity_verified"])

    def test_rejects_duplicates_reordered_shots_and_unknown_cast(self):
        self.bootstrap(3)
        original = json.loads(json.dumps(self.spec))
        for mutator in (
            lambda s: s["shots"][1].update(job_id=s["shots"][0]["job_id"]),
            lambda s: s["shots"][0].update(shot_id="sh-00003"),
            lambda s: s["shots"][0].update(character_ids=["unknown"]),
            lambda s: s["shots"][0].update(caption="bad\n00:00:00,001 --> 09:00:00,000"),
            lambda s: s.update(plan_sha="f" * 64),
        ):
            with self.subTest(mutator=str(mutator)):
                self.spec = json.loads(json.dumps(original))
                mutator(self.spec)
                with self.assertRaises((ValueError, PermissionError)):
                    self.propose()

    def test_revision_reuses_unchanged_motion_clips_and_blocks_noop(self):
        self.bootstrap(3)
        previous = self.propose()
        next_spec = json.loads(json.dumps(self.spec))
        next_spec["episode_id"] = "episode-two"
        next_spec["source_episode_id"] = "episode-one"
        next_spec["source_sha256"] = previous["episode_sha256"]
        with self.assertRaises(production.FilmProductionError):
            production.prepare(next_spec, film_root=self.films, db_path=self.db)
        next_spec["shots"][0]["caption"] = "Lời dẫn mới cho cảnh một."
        new = production.prepare(next_spec, film_root=self.films, db_path=self.db)
        self.assertNotEqual(new["episode_sha256"], previous["episode_sha256"])
        self.assertEqual(len(list((self.films / "fox-film" / "motion_clips").iterdir())), 3)
        self.assertFalse((self.films / "fox-film" / "productions" /
                          "episode-one" / "episode.mp4").exists())

    def _render_mock(self, *, with_audio=False, proposal=None):
        if proposal is None:
            self.bootstrap(3)
            proposal = self.propose()
        folder = self.films / "fox-film" / "productions" / "episode-one"
        if with_audio:
            self.generate_voice(proposal)
        cmds = []
        def fake(args, timeout):
            cmds.append(args)
            self.assertIn("-filter_complex", args)
            self.assertIn("concat=n=3:v=1:a=0[outv]", args[args.index("-filter_complex") + 1])
            self.assertEqual(args[args.index("-frames:v")+1], "147")
            self.assertNotIn("shell", args)
            Path(args[-1]).write_bytes(b"faked-assembled-mp4" * 300)
        qa = {"codec": "h264", "width": 640, "height": 352,
              "frames_decoded": 147, "fps": 12, "duration_seconds": 12.25,
              "audio_codec": "aac", "full_decode_pass": True}
        with patch.object(production.ops_control, "require_active"), \
             patch.object(production, "_run", side_effect=fake), \
             patch.object(production, "_probe_master", return_value=qa):
            outcome = production.render(
                "episode-one", "fox-film", proposal["episode_sha256"],
                confirmed=True, film_root=self.films, db_path=self.db)
        self.assertEqual(len(cmds), 1)
        self.assertEqual(outcome["status"], production.READY)
        self.assertFalse(outcome["video_accepted"])
        self.assertFalse(outcome["visual_continuity_verified"])
        self.assertFalse(outcome["published"])
        record = production.inspect_render("episode-one", "fox-film", film_root=self.films)
        self.assertEqual(record["video_sha256"], outcome["video_sha256"])
        with self.assertRaises(FileExistsError):
            with patch.object(production.ops_control, "require_active"):
                production.render(
                    "episode-one", "fox-film", proposal["episode_sha256"],
                    confirmed=True, film_root=self.films, db_path=self.db)
        return folder

    def test_owner_gated_ffmpeg_render_and_receipt(self):
        self.bootstrap(3)
        p = self.propose()
        with patch("subprocess.run") as run:
            with self.assertRaises(PermissionError):
                production.render("episode-one", "fox-film", p["episode_sha256"],
                                  film_root=self.films, db_path=self.db)
            run.assert_not_called()
        folder = self._render_mock(proposal=p)
        (folder / "episode.mp4").write_bytes(b"tampered")
        with self.assertRaises(production.FilmProductionError):
            production.inspect_render("episode-one", "fox-film", film_root=self.films)

    def generate_voice(self, proposal):
        folder = self.films / "fox-film" / "productions" / "episode-one"
        def fake(command, *, cwd, timeout, input_text=None):
            self.assertEqual(cwd, folder)
            with wave.open(str(folder / "voiceover.partial.wav"), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\0\0" * 16000 * 2)
        with patch.object(production.ops_control, "require_active"), \
             patch.object(production.media_render, "_voice_command",
                          return_value=(["piper"], None)), \
             patch.object(production.media_render, "_run_process", side_effect=fake):
            return production.voice("episode-one", "fox-film", proposal["episode_sha256"],
                                    engine="piper", voice_name="vietnamese.onnx",
                                    confirmed=True, film_root=self.films)

    def test_optional_offline_tts_requires_owner_then_reuses_verified_audio(self):
        self.bootstrap(3)
        proposal = self.propose()
        with patch("subprocess.run") as run:
            with self.assertRaises(PermissionError):
                production.voice("episode-one", "fox-film", proposal["episode_sha256"],
                                 engine="piper", confirmed=False, film_root=self.films)
            run.assert_not_called()
        result = self.generate_voice(proposal)
        self.assertFalse(result["voice_language_verified"])
        with self.assertRaises(FileExistsError):
            self.generate_voice(proposal)
        record = production._voice_receipt(
            self.films / "fox-film" / "productions" / "episode-one",
            proposal["episode_sha256"], 12.25)
        self.assertEqual(record["voice_sha256"], result["voice_sha256"])
        voice_file = self.films / "fox-film" / "productions" / "episode-one" / "voiceover.wav"
        voice_file.write_bytes(b"tampered")
        with self.assertRaises((ValueError, EOFError, wave.Error)):
            production._voice_receipt(
                voice_file.parent, proposal["episode_sha256"], 12.25)

    def test_final_master_ffprobe_requires_real_frame_audio_and_duration(self):
        metadata = {
            "streams": [{"codec_name": "h264", "width": 640, "height": 352,
                         "avg_frame_rate": "12/1", "nb_read_frames": "147"}],
            "format": {"duration": "12.250", "format_name": "mov,mp4,m4a"},
        }
        audio = {"streams": [{"codec_name": "aac", "sample_rate": "16000",
                              "channels": 1}]}
        def stdout(info):
            return json.dumps(info).encode("utf-8")
        path = Path("trusted-master.mp4")
        with patch.object(production.motion_verify, "_run",
                          side_effect=[stdout(metadata), stdout(audio)]) as probe, \
             patch.object(production, "_run") as decoded:
            report = production._probe_master(path, 3)
            self.assertEqual(report["frames_decoded"], 147)
            self.assertTrue(report["full_decode_pass"])
            decoded.assert_called_once()
            self.assertIn("0:a:0", decoded.call_args.args[0])
            self.assertEqual(probe.call_count, 2)
        for change in (
            {"streams": [{**metadata["streams"][0], "nb_read_frames": "146"}]},
            {"format": {"duration": "999.0", "format_name": "mov,mp4"}},
        ):
            damaged = json.loads(json.dumps(metadata))
            damaged.update(change)
            with self.subTest(change=change), \
                 patch.object(production.motion_verify, "_run",
                              side_effect=[stdout(damaged), stdout(audio)]), \
                 patch.object(production, "_run") as decoded:
                with self.assertRaises(production.FilmProductionError):
                    production._probe_master(path, 3)
                decoded.assert_not_called()
        with patch.object(production.motion_verify, "_run",
                          side_effect=[stdout(metadata), stdout({"streams": []})]), \
             patch.object(production, "_run") as decoded:
            with self.assertRaises(production.FilmProductionError):
                production._probe_master(path, 3)
            decoded.assert_not_called()

    def test_prop_change_needs_owner_transition_note(self):
        self.bootstrap(3)
        self.spec["shots"][1]["prop_ids"] = []
        with self.assertRaisesRegex(production.FilmProductionError, "Location/props"):
            self.propose()
        self.spec["shots"][1]["change_note"] = "Map was left on the river bank."
        self.spec["shots"][2]["prop_ids"] = []
        self.propose()

    def test_ffmpeg_failure_does_not_commit_video_or_replace_clip(self):
        self.bootstrap(3)
        p = self.propose()
        folder = self.films / "fox-film" / "productions" / "episode-one"
        with patch.object(production.ops_control, "require_active"), \
             patch.object(production, "_run",
                          side_effect=production.FilmProductionError("ffmpeg failed")):
            with self.assertRaises(production.FilmProductionError):
                production.render("episode-one", "fox-film", p["episode_sha256"],
                                  confirmed=True, film_root=self.films, db_path=self.db)
        self.assertFalse((folder / "render-receipt.json").exists())
        self.assertFalse((folder / "episode.mp4").exists())
        self.assertFalse((folder / "captions.srt").exists())
        self.assertEqual(len(list((self.films / "fox-film" / "motion_clips").iterdir())), 3)




class Wave9FilmHttpTests(unittest.TestCase):
    """Authentication, reviewed manifest SHA, CSRF and external mode gates."""

    def setUp(self):
        from tests.test_webapp_revision_http_v41 import WebappRevisionHttpTests
        fixture = WebappRevisionHttpTests(
            "test_get_requires_login_and_allows_signed_source_review")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.http = fixture
        self.slug = "fox-film"
        self.episode = "episode-one"
        self.sha = "d" * 64
        self.plan = {
            "film_slug": self.slug, "episode_id": self.episode,
            "episode_sha256": self.sha, "status": "PREPARED_NOT_RENDERED",
            "shots": [{"shot_id": "sh-00001"}], "shot_count": 3,
            "runtime_seconds": 12.25,
        }

    def test_read_owner_auth_review_then_ffmpeg_execution_gate(self):
        uri = "/api/film/productions"
        item = uri + "/" + self.slug + "/" + self.episode
        payload = {"ack": "ASSEMBLE_LOCAL_FILM", "film_slug": self.slug,
                   "episode_id": self.episode, "episode_sha": self.sha}
        with patch.object(production, "list_episodes", return_value=[]), \
             patch.object(production, "inspect", return_value=self.plan), \
             patch.object(production, "_folder", return_value=Path(self.http.brain).parent / "none"), \
             patch.object(production, "render",
                          return_value={"status": production.READY,
                                        "video_accepted": False}) as composer, \
             patch.object(production.ops_control, "require_active"):
            self.assertEqual(self.http.req("GET", uri)[0], 401)
            self.http.login()
            code, result, _ = self.http.req("GET", uri)
            self.assertEqual(code, 200)
            self.assertFalse(result["visual_continuity_verified"])
            self.assertEqual(self.http.req("POST", uri + "/render", payload)[0], 400)
            self.http.server.allow_external_actions = True
            self.assertEqual(self.http.req("POST", uri + "/render", payload)[0], 400)
            status, result, _ = self.http.req("GET", item)
            self.assertEqual(status, 200, result)
            self.assertEqual(result["proposal"]["episode_sha256"], self.sha)
            self.assertEqual(self.http.req("POST", uri + "/render",
                                            payload, csrf=False)[0], 403)
            self.assertEqual(self.http.req("POST", uri + "/render",
                            {**payload, "episode_sha": "f"*64})[0], 400)
            self.assertEqual(self.http.req("POST", uri + "/render",
                            {**payload, "ack": "WRONG"})[0], 400)
            composer.assert_not_called()
            status, result, _ = self.http.req("POST", uri + "/render", payload)
            self.assertEqual(status, 200, result)
            self.assertFalse(result["video_accepted"])
            composer.assert_called_once_with(
                self.episode, self.slug, self.sha, confirmed=True)

    def test_offline_tts_requires_review_and_engine_allowlist(self):
        uri = "/api/film/productions"
        item = uri + "/" + self.slug + "/" + self.episode
        req = {"ack": "SYNTHESIZE_LOCAL_VOICE", "film_slug": self.slug,
               "episode_id": self.episode, "episode_sha": self.sha,
               "engine": "piper", "voice_name": "owner-vi.onnx"}
        self.http.login()
        self.http.server.allow_external_actions = True
        with patch.object(production, "inspect", return_value=self.plan), \
             patch.object(production, "_folder", return_value=Path(self.http.brain).parent / "none"), \
             patch.object(production, "voice",
                          return_value={"status": "LOCAL_TTS_CREATED_REVIEW_REQUIRED",
                                        "voice_language_verified": False}) as synth, \
             patch.object(production.ops_control, "require_active"):
            self.assertEqual(self.http.req("POST", uri + "/voice", req)[0], 400)
            self.assertEqual(self.http.req("GET", item)[0], 200)
            self.assertEqual(self.http.req("POST", uri + "/voice",
                            {**req, "engine": "remote_tts"})[0], 400)
            synth.assert_not_called()
            status, result, _ = self.http.req("POST", uri + "/voice", req)
            self.assertEqual(status, 200, result)
            self.assertFalse(result["voice_language_verified"])
            synth.assert_called_once()


if __name__ == "__main__":
    unittest.main()
