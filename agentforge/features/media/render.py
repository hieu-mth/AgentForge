"""Small trusted FFmpeg and offline voice helpers used by Film Studio.

No legacy storyboard/slideshow pipeline, network, auto model download or
arbitrary subprocess execution. Callers must pass signed Owner-approved jobs.
"""
import os
import re
import shutil
import subprocess

from agentforge.paths import REPOSITORY_ROOT, ensure_local_root

VOICE_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        binary = shutil.which("ffmpeg")
        if binary is None:
            raise RuntimeError("FFmpeg missing: install the explicit [media] extra")
        return binary


def _run_process(args, *, cwd, timeout=180, input_text=None):
    result = subprocess.run(
        args, cwd=cwd, input=input_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=False, timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Local media process failed (exit {result.returncode})")
    return result


def _voice_command(engine, folder, voice):
    folder = ensure_local_root(folder)
    if engine == "windows":
        if os.name != "nt":
            raise RuntimeError("Windows SAPI TTS is only available on Windows")
        binary = shutil.which("powershell.exe")
        if not binary:
            raise RuntimeError("Windows PowerShell not installed")
        script = ensure_local_root(REPOSITORY_ROOT / "scripts" / "local_tts_windows.ps1")
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
            raise ValueError("Piper needs the exact flat .onnx voice filename")
        model = ensure_local_root(REPOSITORY_ROOT / "models" / "voices" / voice)
        if not model.is_file() or not model.with_suffix(".onnx.json").is_file():
            raise RuntimeError("Piper voice model and JSON config are required")
        return [executable, "--model", str(model),
                "--output_file", str(folder / "voiceover.partial.wav")], (
                    folder / "narration.txt").read_text(encoding="utf-8")
    raise ValueError("Unsupported local TTS engine")
