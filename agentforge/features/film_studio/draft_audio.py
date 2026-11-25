"""Optional Owner-approved local narration aligned to exact Studio shot boundaries."""
import hashlib
import tempfile
import wave
from contextlib import contextmanager
from pathlib import Path

from agentforge import ops_control
from agentforge.features.media import render
from agentforge.paths import ensure_local_root

SAMPLE_RATE = 48000


def plan(engine, voice_name):
    if not isinstance(voice_name, str) or len(voice_name) > 100 or any(ord(c) < 32 for c in voice_name):
        raise ValueError("Invalid local voice name")
    if engine == "none":
        if voice_name:
            raise ValueError("Disable narration without a voice name")
        return None
    if engine not in ("windows", "piper") or voice_name.startswith("-"):
        raise ValueError("Unsupported local narration engine or voice")
    if engine == "piper" and (not render.VOICE_RE.fullmatch(voice_name) or not voice_name.endswith(".onnx")):
        raise ValueError("Piper needs the exact installed .onnx voice filename")
    return {"engine": engine, "voice_name": voice_name}


def validate(job):
    audio = job.get("audio_plan")
    if audio is None:
        return None
    if not isinstance(audio, dict) or audio.keys() != {"engine", "voice_name"}:
        raise ValueError("Invalid narration plan")
    checked = plan(audio["engine"], audio["voice_name"])
    if checked is None or not any(scene.get("caption", "").strip() for scene in job["board"]["scenes"]):
        raise ValueError("Cần ít nhất một phụ đề có nội dung để tạo lời thoại.")
    return checked


def _pcm_duration(path):
    ensure_local_root(path)
    if not path.is_file() or not 44 <= path.stat().st_size <= 32_000_000:
        raise ValueError("Local narration WAV is missing or oversized")
    try:
        with wave.open(str(path), "rb") as stream:
            if (stream.getcomptype() != "NONE" or stream.getsampwidth() != 2
                    or stream.getnchannels() not in (1, 2) or not 8000 <= stream.getframerate() <= SAMPLE_RATE
                    or stream.getnframes() <= 0):
                raise ValueError("Only valid 16-bit PCM local narration is supported")
            # Reading all declared frames catches truncated PCM data.
            count = stream.getnframes()
            if len(stream.readframes(count)) != count * stream.getnchannels() * 2:
                raise ValueError("Truncated local narration WAV")
            return count / stream.getframerate()
    except (OSError, wave.Error, EOFError, ZeroDivisionError):
        raise ValueError("Invalid local narration WAV") from None


def _hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def prepare(job, folder, fps):
    audio = validate(job)
    if audio is None:
        yield None
        return
    with tempfile.TemporaryDirectory(dir=folder, prefix="narration-") as tmp:
        root = ensure_local_root(Path(tmp))
        args = [render._ffmpeg(), "-nostdin", "-n", "-v", "error"]
        filters, streams, receipts = [], [], []
        frame_offset = 0
        input_index = 0
        for i, scene in enumerate(job["board"]["scenes"]):
            ops_control.require_active()
            end = frame_offset + scene["frames"]
            samples = round(end * SAMPLE_RATE / fps) - round(frame_offset * SAMPLE_RATE / fps)
            frame_offset = end
            caption = scene.get("caption", "").strip()
            if caption:
                shot = ensure_local_root(root / f"shot-{i+1:02d}")
                shot.mkdir()
                (shot / "narration.txt").write_text(caption, encoding="utf-8")
                cmd, stdin = render._voice_command(audio["engine"], shot, audio["voice_name"])
                render._run_process(cmd, cwd=shot, timeout=150, input_text=stdin)
                wav = ensure_local_root(shot / "voiceover.partial.wav")
                seconds = _pcm_duration(wav)
                if seconds > samples / SAMPLE_RATE:
                    raise ValueError(f"Lời thoại cảnh {i+1} dài hơn thời lượng cảnh. Hãy rút ngắn phụ đề.")
                args += ["-i", str(wav)]
                filters.append(f"[{input_index}:a]aresample={SAMPLE_RATE},aformat=sample_fmts=s16:channel_layouts=mono,"
                               f"apad=whole_len={samples},atrim=end_sample={samples},asetpts=PTS-STARTPTS[a{i}]")
                input_index += 1
                receipts.append({"shot_id": scene["shot_id"], "source_sha256": _hash(wav),
                                 "caption_sha256": hashlib.sha256(caption.encode("utf-8")).hexdigest(),
                                 "duration_seconds": round(seconds, 3), "allocated_samples": samples})
            else:
                filters.append(f"anullsrc=r={SAMPLE_RATE}:cl=mono,atrim=end_sample={samples},"
                               f"asetpts=PTS-STARTPTS[a{i}]")
                receipts.append({"shot_id": scene["shot_id"], "source_sha256": None,
                                 "allocated_samples": samples})
            streams.append(f"[a{i}]")
        filters.append("".join(streams) + f"concat=n={len(streams)}:v=0:a=1[out]")
        output = ensure_local_root(root / "narration.wav")
        render._run_process(args + ["-filter_complex_threads", "1", "-filter_complex", ";".join(filters),
                                    "-map", "[out]", "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE),
                                    "-ac", "1", str(output)], cwd=root, timeout=120)
        _pcm_duration(output)
        expected = round(frame_offset * SAMPLE_RATE / fps)
        with wave.open(str(output), "rb") as stream:
            if (stream.getframerate() != SAMPLE_RATE or stream.getnchannels() != 1
                    or stream.getnframes() != expected):
                raise ValueError("Narration track does not match the approved timeline")
        yield {"path": output, "evidence": {"kind": "owner_local_caption_tts", **audio,
               "sample_rate": SAMPLE_RATE, "samples": expected, "source_sha256": _hash(output),
               "shots": receipts, "voice_language_verified": False,
               "source_wav_retained": False}}
