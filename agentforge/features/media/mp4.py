"""Bounded structural and technical MP4 verification for Film Studio."""
import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path

from agentforge.features.media import render

MAX_VIDEO_BYTES = 160 * 1024 * 1024


def _mp4_structural(path):
    path = Path(path)
    """Read enough ISO-BMFF structure to require audio and video tracks."""
    size = path.stat().st_size
    if size < 512 or size > 160_000_000:
        raise ValueError("MP4 outside allowed size range")
    with path.open("rb") as fd:
        box_types = set()
        moov = b""
        pos = 0
        while pos + 8 <= size:
            fd.seek(pos)
            header = fd.read(16)
            length = int.from_bytes(header[:4], "big")
            name = header[4:8]
            header_size = 8
            if length == 1:
                length = int.from_bytes(header[8:16], "big")
                header_size = 16
            if length == 0:
                length = size - pos
            if length < header_size or pos + length > size:
                raise ValueError("MP4 box boundary invalid")
            box_types.add(name)
            if name == b"moov":
                if length > 2_000_000:
                    raise ValueError("MP4 metadata too large")
                fd.seek(pos + header_size)
                moov = fd.read(length - header_size)
            pos += length
    if not {b"ftyp", b"moov", b"mdat"}.issubset(box_types):
        raise ValueError("MP4 missing expected structural boxes")
    if b"vide" not in moov or b"soun" not in moov:
        raise ValueError("MP4 missing video or audio track")
    return {"container": "mp4", "audio_track_present": True,
            "video_track_present": True, "structure_only": True}


def verify_video(path, seconds, *, fps, resolution, require_audio=False):
    """Verify a normalized video against its explicit execution contract."""
    if not 1024 <= path.stat().st_size <= MAX_VIDEO_BYTES:
        raise ValueError("MP4 outside permitted size range.")
    ffprobe = render.find_media_tool("ffprobe")
    if not ffprobe:
        raise ValueError("ffprobe required.")
    meta = render._run_process([ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate", "-of", "json", str(path)],
        cwd=path.parent, timeout=30)
    video = json.loads(meta.stdout)["streams"][0]
    if (video["width"], video["height"]) != tuple(resolution) or Fraction(video["avg_frame_rate"]) != fps:
        raise ValueError("Video output does not match the approved profile.")
    decoded = render._run_process([render._ffmpeg(), "-nostdin", "-v", "error", "-xerror",
        "-i", str(path), "-map", "0:v:0", "-progress", "pipe:1", "-f", "null", "-"],
        cwd=path.parent, timeout=90)
    frames = re.findall(r"(?m)^frame=(\d+)", decoded.stdout)
    if not frames or int(frames[-1]) != seconds * fps:
        raise ValueError("Video frame count differs from approved duration.")
    if require_audio:
        render._run_process([render._ffmpeg(), "-nostdin", "-v", "error", "-xerror", "-i", str(path),
                             "-map", "0:a:0", "-f", "null", "-"], cwd=path.parent, timeout=90)
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
