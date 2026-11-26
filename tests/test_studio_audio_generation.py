import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentforge.ai import model_hub, orchestrator_policy
from agentforge.features.film_studio import audio_director, studio_audio_generation as generation


class AudioGenerationTests(unittest.TestCase):
    def test_transport_uses_explicit_model_and_correct_duration(self):
        profile = {"provider": "elevenlabs", "model": "owner-model"}
        for kind, route, expected in (
            ("sfx", "/sound-generation", {"text": "rain", "duration_seconds": .5, "loop": False}),
            ("music", "/music", {"prompt": "rain", "music_length_ms": 3000, "force_instrumental": True}),
        ):
            with (self.subTest(kind=kind),
                  patch.object(generation.studio_cloud, "_connection", return_value=(
                    SimpleNamespace(hostname="example.test", port=443), "/v1", {"Authorization": "Bearer fixture"})),
                  patch.object(generation.http.client, "HTTPSConnection") as connection):
                client = connection.return_value
                client.getresponse.return_value.status = 200
                raw = b"ID3" + b"x"*200
                client.getresponse.return_value.read.return_value = raw
                self.assertEqual(generation.generate(profile, kind, "rain", .25), raw)
                args, kwargs = client.request.call_args
                self.assertEqual(args, ("POST", "/v1"+route+"?output_format=mp3_44100_128"))
                self.assertEqual(kwargs["headers"]["xi-api-key"], "fixture")
                self.assertNotIn("Authorization", kwargs["headers"])
                self.assertEqual(json.loads(kwargs["body"]), {"model_id": "owner-model", **expected})
                client.close.assert_called_once()

    def test_generation_requires_route_and_explicit_owner_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hub.sqlite3"
            self.assertIsNone(model_hub.audio_generation_binding("film.sound", db_path=db, optional=True))
            profile = {"id": "owner_sound", "provider": "elevenlabs", "enabled": True,
                       "model": "owner-model", "base_url_env": "ELEVENLABS_BASE_URL",
                       "api_key_env": "ELEVENLABS_API_KEY"}
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, db_path=db, profile=profile)
            policy = orchestrator_policy.defaults()
            model_hub.change("SET_MODEL_ROUTE", expected_revision=1, db_path=db,
                             task_id="film.sound", model_ref="owner_sound")
            with self.assertRaises(PermissionError):
                model_hub.audio_generation_binding("film.sound", db_path=db)
            policy.update(permissions=dict.fromkeys(policy["permissions"], True), tools=["ffmpeg"])
            model_hub.change("SAVE_ORCHESTRATOR", expected_revision=2, db_path=db, policy=policy)
            self.assertEqual(model_hub.audio_generation_binding("film.sound", db_path=db)[1]["id"], "owner_sound")

    def test_generated_audio_decodes_mixes_and_reserves_budget(self):
        from agentforge.features.film_studio import draft_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp3 = root / "fixture.mp3"
            ffmpeg = audio_director.render._ffmpeg()
            audio_director.render._run_process([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi",
                "-i", "sine=frequency=440:sample_rate=44100:duration=1", "-c:a", "libmp3lame",
                str(mp3)], cwd=root)
            job = {"brief": {"idea": "Rain"}, "cast": {}, "board": {"scenes": [
                {"shot_id": "one", "frames": 48, "character_ids": []}]}}
            cue = {"kind": "sfx", "start_frame": 0, "end_frame": 24, "gain_db": -10,
                   "speaker": "", "text": "Rain on a roof", "asset": ""}
            profile = {"id": "owner_sound", "provider": "elevenlabs", "model": "fixture"}
            def binding(route, **kwargs):
                return (1, profile, 1) if route == "film.sound" else None
            with (patch.object(audio_director, "library", return_value={}),
                  patch.object(model_hub, "audio_generation_binding", side_effect=binding),
                  patch.object(audio_director.ops_control, "require_active"),
                  patch.object(draft_pipeline, "_save") as save,
                  patch.object(generation, "generate", return_value=mp3.read_bytes()) as call):
                job["audio_plan"] = audio_director.propose(job, "windows", "", {},
                    lambda *args: {"shots": [{"shot_id": "one", "cues": [cue], "unresolved": ""}]},
                    generate=True)
                with audio_director.prepare(job, root, 24) as result:
                    self.assertEqual(result["evidence"]["samples"], 96000)
                    self.assertEqual(result["evidence"]["cues"][0]["generated"]["profile_id"], "owner_sound")
                    with wave.open(str(result["path"]), "rb") as stream:
                        self.assertEqual(stream.getnframes(), 96000)
                self.assertEqual(job["cloud_calls"], 1)
                save.assert_called_once()
                call.assert_called_once()
                with self.assertRaisesRegex(ValueError, "ngân sách"):
                    with audio_director.prepare(job, root, 24):
                        self.fail("Exhausted budget must stop")
                call.assert_called_once()

    def test_generated_cues_are_opt_in_and_pinned(self):
        job = {"brief": {"idea": "Rain"}, "cast": {}, "board": {"scenes": [
            {"shot_id": "one", "frames": 48, "character_ids": []}]}}
        cue = {"kind": "sfx", "start_frame": 0, "end_frame": 24, "gain_db": -10,
               "speaker": "", "text": "Rain hitting a tin roof", "asset": ""}
        infer = lambda *args: {"shots": [{"shot_id": "one", "cues": [cue], "unresolved": ""}]}
        profile = {"id": "owner_sound", "provider": "elevenlabs", "model": "fixture"}
        def binding(route, **kwargs):
            return (1, profile, 10) if route == "film.sound" else None
        with (patch.object(audio_director, "library", return_value={}),
              patch.object(model_hub, "audio_generation_binding", side_effect=binding)):
            with self.assertRaises(ValueError):
                audio_director.propose(job, "windows", "", {}, infer)
            plan = audio_director.propose(job, "windows", "", {}, infer, generate=True)
            self.assertEqual(plan["cues"][0]["generate_route"], "film.sound")
            self.assertEqual(audio_director.validate(job, plan), plan)
            profile["model"] = "changed"
            with self.assertRaisesRegex(ValueError, "model changed"):
                audio_director.validate(job, plan)
