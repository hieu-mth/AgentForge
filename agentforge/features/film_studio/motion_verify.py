"""Wave 8: Owner-approved local ComfyUI MP4 intake and technical QA.

Import is constrained to the unique per-job SaveVideo filename under an
explicitly Owner-configured ComfyUI output directory. Checkpointed ComfyUI
completion is required; generated media never becomes automatically accepted.
All ffprobe/FFmpeg commands are fixed argv (no shell, no network, no retry).
Peak VRAM and real model speed are *not* inferred from static GPU metadata.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from agentforge.features.film_studio import motion_comfy as motion
from agentforge.paths import ensure_local_root

MAX_MP4_BYTES = 160 * 1024 * 1024
MAX_PROBE_BYTES = 16_384
MAX_PROBE_SECONDS = 30
MAX_DECODE_SECONDS = 80
TECHNICAL = "MP4_TECHNICAL_PASS_OWNER_REVIEW_REQUIRED"
MODEL_ID = "wan2.2_ti2v_5B_fp16"
CODECS = frozenset({"h264", "hevc", "av1", "mpeg4"})


class MotionVerificationError(ValueError):
    """Bounded and non-sensitive media verification failure."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(body: dict) -> str:
    return _sha(json.dumps(body, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _job(job_id, db_path):
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise MotionVerificationError("Invalid motion job ID")
    conn = motion._db(db_path)
    if conn is None:
        raise KeyError("Motion job not found")
    with closing(conn):
        row = conn.execute("SELECT * FROM motion_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise KeyError("Motion job not found")
    return dict(row)


def _output_source(root: Path, name: str, job_id: str) -> Path:
    if (not isinstance(name, str) or not re.fullmatch(
            r"af_motion_" + job_id + r"_[0-9]{5}\.mp4", name)):
        raise MotionVerificationError("MP4 filename must match this ComfyUI job")
    root = ensure_local_root(Path(root))
    if not root.is_dir():
        raise MotionVerificationError("Owner ComfyUI output directory is missing")
    source = ensure_local_root(root / name)
    if not source.is_file():
        raise MotionVerificationError("MP4 from this job not found in ComfyUI output")
    length = source.stat().st_size
    if not 1024 <= length <= MAX_MP4_BYTES:
        raise MotionVerificationError("Motion MP4 size exceeds pilot safety bounds")
    return source


def _run(tool: str, args: list[str], *, seconds: int):
    executable = shutil.which(tool)
    if not executable:
        raise MotionVerificationError("FFmpeg and ffprobe must be installed and trusted")
    try:
        result = subprocess.run(
            [executable, *args], stdin=subprocess.DEVNULL, capture_output=True,
            timeout=seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MotionVerificationError("Local MP4 verification tool failed or timed out") from exc
    if result.returncode or len(result.stdout) > MAX_PROBE_BYTES:
        raise MotionVerificationError("MP4 decode/probe failed; not a verified video")
    return result.stdout


def _probe(path: Path):
    raw = _run("ffprobe", [
        "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate,nb_read_frames"
                         ":format=duration,format_name",
        "-of", "json", str(path)], seconds=MAX_PROBE_SECONDS)
    try:
        data = json.loads(raw)
        streams = data["streams"]
        info = data["format"]
        if not isinstance(streams, list) or len(streams) != 1:
            raise ValueError("No exactly one selected video stream")
        stream = streams[0]
        width, height = stream["width"], stream["height"]
        frames = int(stream["nb_read_frames"])
        num, den = (int(x) for x in stream["avg_frame_rate"].split("/"))
        duration = float(info["duration"])
        codec = stream["codec_name"]
        if (type(width) is not int or type(height) is not int
                or width != motion.PROFILE["width"]
                or height != motion.PROFILE["height"]
                or frames != motion.PROFILE["frames"]
                or den == 0 or num / den != motion.PROFILE["fps"]
                or not math.isfinite(duration) or not 3.8 <= duration <= 4.5
                or codec not in CODECS
                or "mp4" not in info["format_name"]):
            raise ValueError("Clip is outside bounded 4-second profile")
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise MotionVerificationError("MP4 metadata does not meet fixed pilot profile") from exc
    _run("ffmpeg", ["-hide_banner", "-nostdin", "-v", "error",
                    "-xerror", "-threads", "2", "-i", str(path),
                    "-map", "0:v:0", "-f", "null", "-"],
         seconds=MAX_DECODE_SECONDS)
    return {"codec": codec, "width": width, "height": height,
            "frames_decoded": frames, "fps": motion.PROFILE["fps"],
            "duration_seconds": round(duration, 3)}


def _dir(row, film_root):
    film_slug = row["film_slug"]
    motion.long_form._id(film_slug, "film slug")
    folder = Path(film_root) / film_slug / "motion_clips" / row["job_id"]
    ensure_local_root(folder)
    return folder


def inspect_receipt(job_id, *, film_root=motion.FILMS, db_path=motion.DB):
    row = _job(job_id, db_path)
    folder = _dir(row, film_root)
    report = folder / "receipt.json"
    ensure_local_root(report)
    if not report.is_file():
        raise KeyError("MP4 import receipt not found")
    if not 2 <= report.stat().st_size <= 12_000:
        raise MotionVerificationError("Motion receipt corrupted")
    try:
        value = json.loads(report.read_text(encoding="utf-8"))
        keys = {"format", "job_id", "film_slug", "shot_id", "plan_sha",
                "workflow_sha", "prompt_sha", "seed", "provider_id", "model_id",
                "state", "clip_sha256", "bytes", "technical", "imported_at",
                "wall_seconds_from_submission_to_import", "owner_reported_peak_vram_gib",
                "peak_vram_automatically_measured", "motion_quality_verified",
                "owner_watched", "video_accepted", "youtube_uploaded", "receipt_sha256"}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("Invalid receipt fields")
        digest = value["receipt_sha256"]
        if (not isinstance(digest, str) or not motion.SHA.fullmatch(digest)
                or _digest({k: v for k, v in value.items() if k != "receipt_sha256"}) != digest
                or value["job_id"] != job_id or value["film_slug"] != row["film_slug"]
                or value["shot_id"] != row["shot_id"]
                or value["plan_sha"] != row["plan_sha"]
                or value["workflow_sha"] != row["workflow_sha"]
                or value["provider_id"] != row["provider_id"]
                or value["prompt_sha"] != row["prompt_sha"]
                or value["seed"] != row["seed"]
                or value["format"] != "agentforge.film.motion.receipt.v1"
                or value["state"] != TECHNICAL or value["model_id"] != MODEL_ID
                or any(value[k] is not False for k in
                       ("peak_vram_automatically_measured", "motion_quality_verified",
                        "owner_watched", "video_accepted", "youtube_uploaded"))):
            raise ValueError("Invalid receipt contents")
        clip = folder / "clip.mp4"
        ensure_local_root(clip)
        if not clip.is_file() or clip.stat().st_size != value["bytes"]:
            raise ValueError("Saved MP4 does not match receipt")
        digest_clip = hashlib.sha256()
        with clip.open("rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest_clip.update(block)
        if digest_clip.hexdigest() != value["clip_sha256"]:
            raise ValueError("Saved MP4 SHA changed")
    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise MotionVerificationError("MP4 receipt or saved clip fails integrity check") from exc
    return value


def list_jobs(*, db_path=motion.DB, film_root=motion.FILMS, limit=12):
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("Invalid limit")
    conn = motion._db(db_path)
    if conn is None:
        return []
    with closing(conn):
        rows = [dict(row) for row in conn.execute(
            "SELECT job_id, film_slug, shot_id, plan_sha, workflow_sha, "
            "state, provider_id, created_at FROM motion_jobs "
            "ORDER BY created_at DESC, job_id DESC LIMIT ?", (limit,))]
    result = []
    for item in rows:
        receipt_state = None
        try:
            if item["state"] == "COMPLETE_UNVERIFIED":
                receipt_state = inspect_receipt(item["job_id"], db_path=db_path,
                                                film_root=film_root)["state"]
        except KeyError:
            pass
        except MotionVerificationError:
            receipt_state = "INTEGRITY_REVIEW_REQUIRED"
        result.append({**item, "status": receipt_state or item["state"],
                       "mp4_technical_verified": receipt_state == TECHNICAL})
    return result


def import_clip(*, job_id: str, filename: str, output_dir: Path,
                confirmed=False, owner_reported_peak_vram_gib=None,
                film_root=motion.FILMS, db_path=motion.DB):
    if confirmed is not True:
        raise PermissionError("Owner must explicitly confirm import of a local GPU MP4")
    motion.ops_control.require_active()
    row = _job(job_id, db_path)
    if row["state"] != "COMPLETE_UNVERIFIED" or not row["provider_id"]:
        raise PermissionError("ComfyUI history must confirm terminal success first")
    if (owner_reported_peak_vram_gib is not None and
            (type(owner_reported_peak_vram_gib) not in (int, float)
             or not math.isfinite(owner_reported_peak_vram_gib)
             or not 0 < owner_reported_peak_vram_gib <= 128)):
        raise MotionVerificationError("Peak VRAM must be a real Owner-observed GiB value")
    source = _output_source(output_dir, filename, job_id)
    folder = _dir(row, film_root)
    if folder.exists():
        raise FileExistsError("Motion receipt or staging already exists; never overwrite")
    folder.mkdir(parents=True, exist_ok=False)
    destination = folder / "clip.mp4"
    ensure_local_root(destination)
    digest = hashlib.sha256()
    length = 0
    committed = False
    try:
        with source.open("rb") as inp, destination.open("xb") as out:
            while True:
                block = inp.read(1024 * 1024)
                if not block:
                    break
                length += len(block)
                if length > MAX_MP4_BYTES:
                    raise MotionVerificationError("MP4 exceeds pilot byte budget")
                out.write(block)
                digest.update(block)
        if length != source.stat().st_size or length < 1024:
            raise MotionVerificationError("MP4 changed during local import")
        technical = _probe(destination)
        elapsed = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(row["created_at"])).total_seconds()
        body = {"format": "agentforge.film.motion.receipt.v1",
                "job_id": job_id, "film_slug": row["film_slug"],
                "shot_id": row["shot_id"], "plan_sha": row["plan_sha"],
                "workflow_sha": row["workflow_sha"],
                "prompt_sha": row["prompt_sha"], "seed": row["seed"],
                "provider_id": row["provider_id"], "model_id": MODEL_ID,
                "state": TECHNICAL, "clip_sha256": digest.hexdigest(),
                "bytes": length, "technical": technical, "imported_at": motion._now(),
                "wall_seconds_from_submission_to_import": round(max(elapsed, 0), 2),
                "owner_reported_peak_vram_gib": owner_reported_peak_vram_gib,
                "peak_vram_automatically_measured": False,
                "motion_quality_verified": False, "owner_watched": False,
                "video_accepted": False, "youtube_uploaded": False}
        receipt = {**body, "receipt_sha256": _digest(body)}
        with (folder / "receipt.json").open("x", encoding="utf-8") as out:
            json.dump(receipt, out, ensure_ascii=False, indent=2)
        committed = True
        return {"job_id": job_id, "status": TECHNICAL,
                "clip_sha256": receipt["clip_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "technical": technical,
                "wall_seconds_from_submission_to_import":
                    receipt["wall_seconds_from_submission_to_import"],
                "peak_vram_automatically_measured": False,
                "owner_reported_peak_vram_gib": owner_reported_peak_vram_gib,
                "motion_quality_verified": False, "video_accepted": False,
                "youtube_uploaded": False,
                "relative_path": str((folder / "clip.mp4").relative_to(film_root)).replace("\\", "/")}
    finally:
        if not committed:
            # No unrelated files can be in this uniquely created job folder.
            if destination.exists():
                destination.unlink()
            receipt_path = folder / "receipt.json"
            if receipt_path.exists():
                receipt_path.unlink()
            folder.rmdir()
