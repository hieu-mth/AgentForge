import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from agentforge.features.film_studio import audio_director as audio


class AudioDirectorTests(unittest.TestCase):
    def test_directed_speech_is_separate_from_caption_and_uses_owner_voice(self):
        job = {"brief": {"idea": "Cat says hello"}, "cast": {"cat": {"name": "Cat"}},
               "board": {"scenes": [{"shot_id": "one", "frames": 48, "caption": "Subtitle",
                                     "character_ids": ["cat"]}]}}
        raw = {"kind": "dialogue", "start_frame": 0, "end_frame": 24, "gain_db": -3,
               "speaker": "cat", "text": "Hello!", "asset": ""}
        with patch.object(audio, "library", return_value={}):
            plan = audio.propose(job, "windows", "", {"cat": "Cat voice"},
                                 lambda *args: {"shots": [{"shot_id": "one", "cues": [raw], "unresolved": ""}]})
        job["audio_plan"] = plan
        self.assertEqual(plan["cues"][0]["voice"], "Cat voice")
        self.assertEqual(plan["cues"][0]["text"], "Hello!")
        self.assertEqual(audio.validate(job, plan), plan)
        job["board"]["scenes"][0]["frames"] = 12
        with self.assertRaises(ValueError):
            audio.validate(job, plan)

    def test_real_mix_with_overlapping_cues_and_local_asset(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(audio, "WORKSPACE_DIR", Path(tmp)):
            root = Path(tmp)
            library = root / "audio-library"
            library.mkdir()
            wav = library / "rain.wav"
            with wave.open(str(wav), "wb") as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
                stream.writeframes(b"\x10\x00"*8000)
            job = {"brief": {"idea": "Rain"}, "cast": {}, "board": {"scenes": [
                {"shot_id": "one", "frames": 48, "description": "Rain", "character_ids": []}]}}
            cue = {"kind": "ambience", "start_frame": 0, "end_frame": 48,
                   "gain_db": -12, "speaker": "", "text": "", "asset": "rain.wav"}
            plan = audio.propose(job, "windows", "", {}, lambda *args: {"shots": [{
                "shot_id": "one", "cues": [cue, dict(cue, kind="sfx", start_frame=12, end_frame=24)],
                "unresolved": ""}]})
            job["audio_plan"] = plan
            with patch.object(audio.ops_control, "require_active"):
                with audio.prepare(job, root, 24) as result:
                    self.assertEqual(result["evidence"]["samples"], 96000)
                    self.assertEqual(len(result["evidence"]["cues"]), 2)
                    with wave.open(str(result["path"]), "rb") as stream:
                        self.assertEqual(stream.getnframes(), 96000)
            wav.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "asset changed"):
                audio.validate(job, plan)
