"""S2 optional local TTS and consented MP4 rendering via bundled FFmpeg.

There is NO auto-download, dynamic shell command, remote URL or publishing.
Windows SAPI requires a preinstalled Vietnamese voice; Piper requires a
preinstalled executable and owner-supplied voice model.
"""
import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

from agentforge import media_assets as assets
from agentforge import media_quality as quality

VOICE_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        exe = shutil.which("ffmpeg")
        if exe is None:
            raise RuntimeError("FFmpeg missing: install the explicit [media] extra")
        return exe


def _save_manifest(folder, manifest):
    path = folder / "manifest.json"
    temporary = folder / "manifest.pending.json"
    assets._safe(path)
    if temporary.exists():
        raise FileExistsError("Previous pending manifest needs manual review")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False, allow_nan=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _run_process(args, *, cwd, timeout=180, input_text=None):
    # Exactly one known binary with a fixed argument list; NEVER shell=True.
    outcome = subprocess.run(
        args, cwd=cwd, input=input_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False, timeout=timeout,
        check=False,
    )
    if outcome.returncode:
        # Don't copy model/source text or input paths into an error message.
        raise RuntimeError(f"Local media process failed (exit {outcome.returncode})")
    return outcome


def render_video(run_id, *, confirm_external_run=False):
    """Encode a captioned slideshow + WAV into MP4, verify both tracks."""
    if confirm_external_run is not True:
        raise PermissionError("Explicit media subprocess confirmation required")
    folder, data = assets.load_manifest(run_id)
    if data.get("video") is not None or (folder / "video.mp4").exists():
        raise FileExistsError("Video already exists; no overwrite/re-encode")
    report = quality.check(run_id)
    if report["status"] != "ASSETS_PASS" or report["failures"]:
        raise assets.MediaError("Media assets must pass QA before video rendering")
    if data.get("voiceover") is not None:
        audio = "voiceover.wav"
    else:
        audio = "ambient.wav"
    visual_plan = assets.validate_visual_plan(data.get("visual_plan"), len(data["scenes"]))
    output = folder / "video.partial.mp4"
    if output.exists():
        raise FileExistsError("Previous incomplete MP4 exists; review required")
    executable = _ffmpeg()
    duration = str(data["duration_seconds"])
    concat = folder / "frames.ffconcat"
    if concat.exists():
        raise FileExistsError("Previous FFmpeg script exists; review required")

    if visual_plan["mode"] == "studio" and data.get("studio_layers_version") == 1:
        # Per-shot inputs are signed locally generated photo/typography layers.
        # The photo alone moves. The alpha typography layer stays motionless.
        # No arbitrary text/path/model output is interpolated into filter syntax.
        inputs, filters = [], []
        motions = {
            "static": "fps=15",
            "slow_zoom": "zoompan=z='min(1+on*0.0003,1.045)':d=1:s=540x960:fps=15",
            "slow_pan": "zoompan=z=1.045:x='min(on*0.14,22)':y='min(on*0.04,10)':d=1:s=540x960:fps=15",
        }
        for i, scene in enumerate(data["scenes"]):
            shot_length = str(scene["duration_seconds"])
            for prefix in ("background", "overlay"):
                name = f"{prefix}_{i+1:02}.png"
                if not (folder / name).is_file():
                    raise assets.MediaError("Missing independently layered studio shot")
                inputs.extend(["-loop", "1", "-framerate", "15",
                               "-t", shot_length, "-i", name])
            filters.append(
                f"[{2*i}:v]{motions[visual_plan['motion']]},"
                f"trim=duration={shot_length},setpts=PTS-STARTPTS[bg{i}]")
            filters.append(
                f"[{2*i+1}:v]fps=15,trim=duration={shot_length},"
                f"setpts=PTS-STARTPTS,format=rgba[tx{i}]")
            filters.append(
                f"[bg{i}][tx{i}]overlay=shortest=1:format=auto,"
                f"format=yuv420p[v{i}]")
        filters.append("".join(f"[v{i}]" for i in range(len(data["scenes"])))
                       + f"concat=n={len(data['scenes'])}:v=1:a=0[outv]")
        inputs.extend(["-i", audio])
        cmd = [executable, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-n", *inputs, "-filter_complex", ";".join(filters),
               "-map", "[outv]", "-map", f"{2*len(data['scenes'])}:a:0"]
        effective_motion = visual_plan["motion"]
    else:
        # Legacy cards have embedded text. Never zoom/pan those full frames:
        # it crops the headline and captions, producing unreadable video.
        images = [f"scene_{i+1:02}.png" for i in range(len(data["scenes"]))]
        sequence = ["ffconcat version 1.0"]
        for scene, frame in zip(data["scenes"], images):
            sequence.extend([f"file '{frame}'", f"duration {scene['duration_seconds']}"])
        sequence.append(f"file '{images[-1]}'")
        concat.write_text("\n".join(sequence) + "\n", encoding="ascii")
        cmd = [executable, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-n", "-safe", "1", "-f", "concat", "-i", concat.name,
               "-i", audio, "-map", "0:v:0", "-map", "1:a:0",
               "-vf", "fps=15,format=yuv420p"]
        effective_motion = "static"
    cmd.extend([
        "-r", "15", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-c:a", "aac", "-b:a", "112k",
        "-af", "apad", "-t", duration, "-movflags", "+faststart",
        "-f", "mp4", output.name,
    ])
    try:
        _run_process(cmd, cwd=folder, timeout=180)
        if not output.is_file() or not 1024 < output.stat().st_size < 160_000_000:
            raise assets.MediaError("FFmpeg produced no valid-sized MP4")
        # Decode all streams; -map selects one audio and one video stream.
        _run_process([executable, "-hide_banner", "-loglevel", "error", "-nostdin",
                      "-i", output.name, "-map", "0:v:0", "-map", "0:a:0",
                      "-f", "null", "-"], cwd=folder, timeout=90)
        final = folder / "video.mp4"
        if final.exists():
            raise FileExistsError("Existing video must not be overwritten")
        output.rename(final)
        digest = assets._sha(final)
        data["artifacts"]["video.mp4"] = digest
        data["video"] = {"file": "video.mp4", "sha256": digest,
                         "decoded_by_ffmpeg": True, "effective_motion": effective_motion,
                         "text_layer_fixed": True, "audio_kind":
                         "voiceover" if audio == "voiceover.wav" else "original_ambient"}
        data["stage"] = "VIDEO_RENDERED"
        _save_manifest(folder, data)
    finally:
        output.unlink(missing_ok=True)
        concat.unlink(missing_ok=True)
    verified = quality.check(run_id)
    if verified["status"] != "VIDEO_PASS":
        raise assets.MediaError("Rendered video failed post-production quality check")
    return {"run_id": run_id, "status": "VIDEO_RENDERED",
            "video_path": str(folder / "video.mp4"),
            "duration_seconds": data["duration_seconds"],
            "audio_kind": data["video"]["audio_kind"],
            "quality_status": verified["status"],
            "video_rendered": True, "published": False}


def _voice_command(engine, folder, voice):
    if engine == "windows":
        if os.name != "nt":
            raise RuntimeError("Windows SAPI TTS is only available on Windows")
        binary = shutil.which("powershell.exe")
        if not binary:
            raise RuntimeError("Windows PowerShell not installed")
        script = assets.ROOT / "scripts" / "s2_tts_windows.ps1"
        assets._safe(script)
        if not script.is_file():
            raise RuntimeError("Trusted Windows TTS adapter script missing")
        return [binary, "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "RemoteSigned",
                "-File", str(script),
                "-TextPath", str(folder / "narration.txt"),
                "-OutputPath", str(folder / "voiceover.partial.wav"),
                "-VoiceName", voice or ""], None
    if engine == "piper":
        executable = shutil.which("piper")
        if not executable:
            raise RuntimeError("Local Piper CLI is not installed")
        if not voice or not VOICE_RE.fullmatch(voice) or not voice.endswith(".onnx"):
            raise assets.MediaError("Piper needs the exact flat .onnx voice filename")
        model = assets.ROOT / "models" / "voices" / voice
        assets._safe(model)
        if not model.is_file():
            raise RuntimeError("Piper voice model not found under models/voices")
        if not (model.with_suffix(".onnx.json")).is_file():
            raise RuntimeError("Matching Piper .onnx.json config missing")
        return [executable, "--model", str(model),
                "--output_file", str(folder / "voiceover.partial.wav")], (
                    folder / "narration.txt").read_text(encoding="utf-8")
    raise assets.MediaError("Unsupported TTS engine")


def make_voiceover(run_id, engine, *, voice=None, confirm_external_run=False):
    """Use only explicit installed offline voice engines; no speech fallback."""
    if confirm_external_run is not True:
        raise PermissionError("Explicit local TTS subprocess confirmation required")
    folder, data = assets.load_manifest(run_id)
    if data.get("video") is not None or data.get("voiceover") is not None:
        raise FileExistsError("Existing video or voiceover cannot be modified")
    if quality.check(run_id)["status"] != "ASSETS_PASS":
        raise assets.MediaError("Cannot TTS an invalid media storyboard")
    if voice is not None and (not isinstance(voice, str) or not VOICE_RE.fullmatch(voice)):
        raise assets.MediaError("Invalid voice name")
    text = ". ".join(scene["caption"] for scene in data["scenes"])
    narration = folder / "narration.txt"
    pending = folder / "voiceover.partial.wav"
    if narration.exists() or pending.exists():
        raise FileExistsError("Previous narration attempt must be inspected")
    narration.write_text(text, encoding="utf-8")
    try:
        command, stdin = _voice_command(engine, folder, voice)
        _run_process(command, cwd=folder, input_text=stdin, timeout=120)
        with wave.open(str(pending), "rb") as wav:
            if wav.getsampwidth() != 2 or wav.getnchannels() not in (1, 2):
                raise assets.MediaError("TTS did not produce 16-bit PCM WAV")
            seconds = wav.getnframes() / wav.getframerate()
        if not .3 < seconds <= data["duration_seconds"]:
            raise assets.MediaError("TTS exceeds storyboard duration; adjust copy/durations")
        path = folder / "voiceover.wav"
        if path.exists():
            raise FileExistsError("Voiceover already exists")
        pending.rename(path)
        digest = assets._sha(path)
        data["artifacts"]["voiceover.wav"] = digest
        data["voiceover"] = {"file": "voiceover.wav", "sha256": digest,
                             "engine": engine, "duration_seconds": seconds}
        _save_manifest(folder, data)
    finally:
        narration.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
    return {"run_id": run_id, "status": "VOICEOVER_CREATED",
            "audio_path": str(folder / "voiceover.wav"),
            "voice_engine": engine, "duration_seconds": seconds,
            "voice_language_verified": False}
