"""Optional narration with real FFmpeg alignment; TTS engine is a deterministic fixture."""
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from agentforge.features.film_studio import draft_audio


class DraftAudioTests(unittest.TestCase):
    def test_plan_is_optional_and_validates_voice(self):
        self.assertIsNone(draft_audio.plan("none", ""))
        self.assertEqual(draft_audio.plan("windows", "Microsoft An"), {
            "engine": "windows", "voice_name": "Microsoft An"})
        for engine, voice in (("cloud", ""), ("piper", "../voice.onnx"), ("windows", "-Bad")):
            with self.subTest(engine=engine), self.assertRaises(ValueError):
                draft_audio.plan(engine, voice)
        with draft_audio.prepare({}, None, 24) as result:
            self.assertIsNone(result)

    def test_narration_is_padded_to_shot_boundaries_without_truncation(self):
        job = {"audio_plan": draft_audio.plan("windows", ""), "board": {"scenes": [
            {"shot_id": "one", "caption": "Mèo", "frames": 24},
            {"shot_id": "two", "caption": "", "frames": 24}]}}
        actual_run = draft_audio.render._run_process
        length = [8000]

        def process(args, *, cwd, **kwargs):
            if args[0] != "fixture-tts":
                return actual_run(args, cwd=cwd, **kwargs)
            with wave.open(str(cwd / "voiceover.partial.wav"), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x01\x00" * length[0])

        with (tempfile.TemporaryDirectory() as tmp,
              patch.object(draft_audio.ops_control, "require_active"),
              patch.object(draft_audio.render, "_voice_command", return_value=(["fixture-tts"], None)),
              patch.object(draft_audio.render, "_run_process", side_effect=process)):
            with draft_audio.prepare(job, Path(tmp), 24) as result:
                self.assertEqual(result["evidence"]["samples"], 96000)
                self.assertEqual(result["evidence"]["shots"][0]["allocated_samples"], 48000)
                self.assertIsNone(result["evidence"]["shots"][1]["source_sha256"])
                with wave.open(str(result["path"]), "rb") as wav:
                    self.assertEqual(wav.getnframes(), 96000)
                    self.assertEqual(wav.getframerate(), 48000)
                path = result["path"]
            self.assertFalse(path.exists())
            length[0] = 32000
            with self.assertRaisesRegex(ValueError, "dài hơn"):
                with draft_audio.prepare(job, Path(tmp), 24):
                    self.fail("Overlong narration must not be truncated")
