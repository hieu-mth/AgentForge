"""Wave 9: local-first film continuity, versioned edit decisions and MP4 assembly.

Only Wave 8 SHA-verified ComfyUI motion clips can enter this pipeline. There
are no model calls, downloads, GPU inference or publishing operations. Film
quality/character identity are NOT inferable from hashes or FFmpeg checks.
All FFmpeg execution requires explicit Owner confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import wave
from contextlib import closing
from pathlib import Path

from agentforge import ops_control
from agentforge.features.film_studio import long_form, motion_comfy, motion_verify
from agentforge.features.media import render as media_render
from agentforge.paths import ensure_local_root

FILMS = motion_comfy.FILMS
DB = motion_comfy.DB
FORMAT = "agentforge.film.production.plan.v1"
OUTPUT_FORMAT = "agentforge.film.production.render.v1"
VOICE_FORMAT = "agentforge.film.production.voice.v1"
SHOT_KEYS = {"shot_id", "job_id", "clip_sha256", "receipt_sha256",
             "character_ids", "location_id", "costume_id", "prop_ids",
             "reference_sha256", "action_camera", "caption", "change_note"}
MAX_SHOTS = 22
FRAME_RATE = 12
FRAMES_PER_SHOT = 49
MIN_MP4 = 1024
MAX_OUTPUT_BYTES = 900_000_000
SHA = re.compile(r"[a-f0-9]{64}\Z")
JOB = re.compile(r"[a-f0-9]{32}\Z")
TAG = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
READY = "ASSEMBLED_TECHNICAL_PASS_OWNER_REVIEW_REQUIRED"


class FilmProductionError(ValueError):
    """An invalid, unsafe, incomplete or stale local production decision."""


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _digest(body):
    return _hash(json.dumps(body, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _text(value, name, length=250, *, optional=False):
    if not isinstance(value, str) or len(value) > length or (
            not optional and not value.strip()) or any(ord(ch) < 32 for ch in value):
        raise FilmProductionError("Invalid " + name)
    return value.strip()


def _tag(value, name):
    if not isinstance(value, str) or not TAG.fullmatch(value):
        raise FilmProductionError("Invalid " + name)
    return value


def _checksum(value, name, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise FilmProductionError("Invalid " + name)
    return value


def _job_id(value):
    if not isinstance(value, str) or not JOB.fullmatch(value):
        raise FilmProductionError("Invalid motion job ID")
    return value


def _folder(film_slug, episode_id, film_root):
    film_slug = long_form._id(film_slug, "film slug")
    episode_id = _tag(episode_id, "episode ID")
    path = Path(film_root) / film_slug / "productions" / episode_id
    return ensure_local_root(path)


def _read_json(path, max_bytes=180_000):
    ensure_local_root(path)
    if not path.is_file() or not 4 <= path.stat().st_size <= max_bytes:
        raise FilmProductionError("Signed production file missing or oversized")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise FilmProductionError("Invalid production JSON") from exc


def _signed(record, key):
    if not isinstance(record, dict) or not isinstance(record.get(key), str):
        raise FilmProductionError("Invalid signed production record")
    value = record[key]
    _checksum(value, key)
    if _digest({k: v for k, v in record.items() if k != key}) != value:
        raise FilmProductionError("Production record fingerprint mismatch")
    return record


def _duration(number):
    return number * FRAMES_PER_SHOT / FRAME_RATE


def _srt_clock(seconds):
    ms = round(seconds * 1000)
    hour, rem = divmod(ms, 3_600_000)
    minute, rem = divmod(rem, 60_000)
    sec, frac = divmod(rem, 1000)
    return f"{hour:02}:{minute:02}:{sec:02},{frac:03}"


def _srt(shots):
    out = []
    for i, shot in enumerate(shots):
        begin, end = _duration(i), _duration(i + 1)
        out.append(f"{i+1}\n{_srt_clock(begin)} --> {_srt_clock(end)}\n"
                   + shot["caption"] + "\n")
    return "\n".join(out) + "\n"


def _check_continuity(shots):
    """Metadata assertions only, NOT visual character recognition."""
    previous = {}
    for index, shot in enumerate(shots):
        # Changing named costume/reference across adjacent appearances is
        # intentional only when an Owner supplies an explicit change note.
        for character in shot["character_ids"]:
            value = (shot["costume_id"], shot["reference_sha256"])
            if (character in previous and previous[character] != value
                    and not shot["change_note"]):
                raise FilmProductionError(
                    "Character costume/reference changed without continuity note")
            previous[character] = value
        if index and shots[index - 1]["location_id"] != shot["location_id"]:
            if not shot["change_note"]:
                raise FilmProductionError(
                    "Location changed without explicit continuity note")
    return {"metadata_checks_pass": True, "visual_continuity_verified": False,
            "identity_model_invoked": False}


def _check_shot(raw, planned, cast_ids):
    if not isinstance(raw, dict) or set(raw) != SHOT_KEYS:
        raise FilmProductionError("Unexpected shot metadata fields")
    if raw["shot_id"] != planned["shot_id"]:
        raise FilmProductionError("Shot order must follow contiguous film plan")
    _job_id(raw["job_id"])
    for field in ("clip_sha256", "receipt_sha256"):
        _checksum(raw[field], field)
    _checksum(raw["reference_sha256"], "reference asset", nullable=True)
    chars, props = raw["character_ids"], raw["prop_ids"]
    if (not isinstance(chars, list) or len(chars) > 8
            or any(type(x) is not str for x in chars)
            or len(chars) != len(set(chars))
            or any(x not in cast_ids for x in chars)):
        raise FilmProductionError("Unknown or duplicated character")
    if (not isinstance(props, list) or len(props) > 12
            or any(type(x) is not str for x in props)
            or len(props) != len(set(props))):
        raise FilmProductionError("Invalid prop identities")
    for item in props:
        _tag(item, "prop ID")
    for name in ("location_id", "costume_id"):
        _tag(raw[name], name)
        if raw[name].startswith("pending-owner-"):
            raise FilmProductionError("Owner must replace draft continuity placeholders")
    _text(raw["action_camera"], "shot action and camera", 500)
    _text(raw["caption"], "subtitle text", 220)
    if (raw["action_camera"].startswith("OWNER REVIEW REQUIRED:")
            or raw["caption"].startswith("OWNER REVIEW REQUIRED:")):
        raise FilmProductionError("Owner must write per-shot action and subtitle")
    _text(raw["change_note"], "continuity change note", 300, optional=True)
    return dict(raw)


def _sources(shots, film_slug, plan_sha, film_root, db_path):
    """Re-read and rehash every Wave 8 receipt + MP4 before a process run."""
    paths = []
    seen = set()
    for shot in shots:
        ident = shot["job_id"]
        if ident in seen:
            raise FilmProductionError("Duplicate clip job; no motion looping")
        seen.add(ident)
        receipt = motion_verify.inspect_receipt(
            ident, film_root=film_root, db_path=db_path)
        if (receipt["film_slug"] != film_slug
                or receipt["plan_sha"] != plan_sha
                or receipt["shot_id"] != shot["shot_id"]
                or receipt["clip_sha256"] != shot["clip_sha256"]
                or receipt["receipt_sha256"] != shot["receipt_sha256"]
                or receipt["state"] != motion_verify.TECHNICAL
                or receipt["technical"].get("frames_decoded") != FRAMES_PER_SHOT
                or receipt["technical"].get("fps") != FRAME_RATE
                or receipt["technical"].get("width") != motion_comfy.PROFILE["width"]
                or receipt["technical"].get("height") != motion_comfy.PROFILE["height"]):
            raise PermissionError("Film clip not proven by matching Wave 8 receipt")
        path = motion_verify._dir(
            {"film_slug": film_slug, "job_id": ident}, film_root) / "clip.mp4"
        ensure_local_root(path)
        paths.append(path)
    return paths


def draft(film_slug, episode_id, *, shot_count, first_shot=1,
          film_root=FILMS, db_path=DB):
    """Build a local JSON editing worksheet from verified motion receipts.

    The worksheet deliberately contains unfinished OWNER REVIEW REQUIRED
    fields that prepare() refuses until the user writes original shot notes.
    No file I/O and no additional GPU tasks, unless CLI --output is used.
    """
    slug = long_form._id(film_slug, "film slug")
    _tag(episode_id, "episode ID")
    if (type(shot_count) is not int or not 3 <= shot_count <= MAX_SHOTS
            or type(first_shot) is not int or first_shot < 1):
        raise FilmProductionError("Draft requires 3–22 shots and a positive first shot")
    plan = long_form.load_plan(film_root, slug)
    planned = plan["shots"][first_shot - 1:first_shot - 1 + shot_count]
    if len(planned) != shot_count or any(s["duration_seconds"] != 4 for s in planned):
        raise FilmProductionError("Film plan has too few full 4-second slots")
    conn = motion_comfy._db(db_path)
    if conn is None:
        raise FilmProductionError("No verified motion jobs are available")
    with closing(conn):
        rows = [dict(row) for row in conn.execute(
            "SELECT job_id, shot_id, state FROM motion_jobs "
            "WHERE film_slug=? AND plan_sha=?", (slug, plan["plan_sha256"]))]
    by_shot = {x["shot_id"]: x for x in rows}
    chapters = {x["id"]: x for x in plan["chapters"]}
    entries = []
    for shot in planned:
        row = by_shot.get(shot["shot_id"])
        if row is None or row["state"] != "COMPLETE_UNVERIFIED":
            raise FilmProductionError(
                "Missing completed motion receipt for shot " + shot["shot_id"])
        receipt = motion_verify.inspect_receipt(
            row["job_id"], film_root=film_root, db_path=db_path)
        if (receipt["film_slug"] != slug
                or receipt["shot_id"] != shot["shot_id"]
                or receipt["plan_sha"] != plan["plan_sha256"]):
            raise PermissionError("Motion clip receipt disagrees with plan")
        entries.append({
            "shot_id": shot["shot_id"], "job_id": row["job_id"],
            "clip_sha256": receipt["clip_sha256"],
            "receipt_sha256": receipt["receipt_sha256"],
            "character_ids": list(chapters[shot["chapter_id"]]["character_ids"]),
            "location_id": "pending-owner-location",
            "costume_id": "pending-owner-costume", "prop_ids": [],
            "reference_sha256": None,
            "action_camera": "OWNER REVIEW REQUIRED: describe original action and camera",
            "caption": "OWNER REVIEW REQUIRED: replace with original subtitles",
            "change_note": "",
        })
    return {"film_slug": slug, "episode_id": episode_id,
            "plan_sha": plan["plan_sha256"], "shots": entries,
            "source_episode_id": None, "source_sha256": None}


def prepare(spec, *, film_root=FILMS, db_path=DB):
    """Create an immutable episode edit decision. No FFmpeg/LLM/GPU invoked."""
    if (not isinstance(spec, dict) or set(spec) !=
            {"film_slug", "episode_id", "plan_sha", "shots",
             "source_episode_id", "source_sha256"}):
        raise FilmProductionError("Unexpected episode plan fields")
    slug = long_form._id(spec["film_slug"], "film slug")
    episode_id = _tag(spec["episode_id"], "episode ID")
    plan = long_form.load_plan(film_root, slug)
    if _checksum(spec["plan_sha"], "plan SHA") != plan["plan_sha256"]:
        raise PermissionError("Film plan changed since Owner review")
    shots = spec["shots"]
    if not isinstance(shots, list) or not 3 <= len(shots) <= MAX_SHOTS:
        raise FilmProductionError("A film production needs 3–22 unique shots")
    first = next((i for i, shot in enumerate(plan["shots"])
                  if shot["shot_id"] == shots[0].get("shot_id")), None) \
        if isinstance(shots[0], dict) else None
    if first is None or len(plan["shots"][first:]) < len(shots):
        raise FilmProductionError("Episode does not match a contiguous planned sequence")
    cast_ids = {c["id"] for c in plan["characters"]}
    validated = []
    for raw, planned in zip(shots, plan["shots"][first:first + len(shots)]):
        if planned["duration_seconds"] != 4:
            raise FilmProductionError("Wave 9 requires full four-second plan slots")
        if (planned["chapter_id"] not in
                {c["id"] for c in plan["chapters"]}):
            raise FilmProductionError("Unknown chapter")
        validated.append(_check_shot(raw, planned, cast_ids))
    _check_continuity(validated)
    _sources(validated, slug, plan["plan_sha256"], film_root, db_path)
    source_id, source_sha = spec["source_episode_id"], spec["source_sha256"]
    if (source_id is None) != (source_sha is None):
        raise FilmProductionError("Both source episode ID and SHA are required")
    if source_id is not None:
        source = inspect(source_id, slug, film_root=film_root)
        if _checksum(source_sha, "parent SHA") != source["episode_sha256"]:
            raise PermissionError("Source version SHA changed")
        if source["plan_sha"] != plan["plan_sha256"] or source["shots"] == validated:
            raise FilmProductionError("Source revision must actually change shot decisions")
    body = {
        "format": FORMAT, "film_slug": slug, "episode_id": episode_id,
        "plan_sha": plan["plan_sha256"], "source_episode_id": source_id,
        "source_sha256": source_sha, "shots": validated, "shot_count": len(shots),
        "runtime_seconds": round(_duration(len(shots)), 3),
        "stage": "PREPARED_NOT_RENDERED", "continuity_metadata_only": True,
        "visual_continuity_verified": False, "published": False,
    }
    document = {**body, "episode_sha256": _digest(body)}
    path = _folder(slug, episode_id, film_root)
    if path.exists():
        raise FileExistsError("Episode version already exists; cannot overwrite")
    path.mkdir(parents=True, exist_ok=False)
    try:
        with (path / "episode-plan.json").open("x", encoding="utf-8") as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
    except BaseException:
        (path / "episode-plan.json").unlink(missing_ok=True)
        path.rmdir()
        raise
    return {"film_slug": slug, "episode_id": episode_id,
            "episode_sha256": document["episode_sha256"],
            "shot_count": len(shots), "runtime_seconds": body["runtime_seconds"],
            "status": body["stage"], "visual_continuity_verified": False,
            "model_calls": 0, "generated_new_clips": False}


def inspect(episode_id, film_slug, *, film_root=FILMS):
    folder = _folder(film_slug, episode_id, film_root)
    record = _signed(_read_json(folder / "episode-plan.json"), "episode_sha256")
    if record.get("format") != FORMAT or record.get("film_slug") != film_slug \
            or record.get("episode_id") != episode_id or record.get("stage") != "PREPARED_NOT_RENDERED" \
            or record.get("published") is not False or record.get("visual_continuity_verified") is not False:
        raise FilmProductionError("Invalid film production plan state")
    plan = long_form.load_plan(film_root, film_slug)
    if plan["plan_sha256"] != record["plan_sha"]:
        raise PermissionError("Film plan SHA no longer matches")
    required = {"format", "film_slug", "episode_id", "plan_sha",
                "source_episode_id", "source_sha256", "shots", "shot_count",
                "runtime_seconds", "stage", "continuity_metadata_only",
                "visual_continuity_verified", "published", "episode_sha256"}
    if (set(record) != required or record.get("continuity_metadata_only") is not True
            or not isinstance(record.get("shots"), list)
            or not 3 <= len(record["shots"]) <= MAX_SHOTS
            or record.get("shot_count") != len(record["shots"])
            or record.get("runtime_seconds") != round(_duration(len(record["shots"])), 3)):
        raise FilmProductionError("Film production metadata mismatch")
    original_shots = plan["shots"]
    first = next((i for i, slot in enumerate(original_shots)
                  if slot["shot_id"] == record["shots"][0].get("shot_id")), None)         if isinstance(record["shots"][0], dict) else None
    if first is None or first + record["shot_count"] > len(original_shots):
        raise FilmProductionError("Production shots are no longer a planned sequence")
    cast_ids = {item["id"] for item in plan["characters"]}
    for raw, slot in zip(record["shots"],
                         original_shots[first:first + record["shot_count"]]):
        if slot["duration_seconds"] != 4:
            raise FilmProductionError("Non-four-second slot cannot enter motion production")
        _check_shot(raw, slot, cast_ids)
    _check_continuity(record["shots"])
    prev = record.get("source_episode_id")
    if prev is not None:
        if prev == episode_id or not isinstance(prev, str) or not TAG.fullmatch(prev):
            raise FilmProductionError("Invalid production ancestry")
        # The digest alone is insufficient: check parent still exists.
        parent = _signed(_read_json(_folder(film_slug, prev, film_root) / "episode-plan.json"),
                         "episode_sha256")
        if parent["episode_sha256"] != record.get("source_sha256"):
            raise PermissionError("Film production parent SHA changed")
    return record


def list_episodes(*, film_root=FILMS, limit=16):
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("Invalid list limit")
    root = ensure_local_root(Path(film_root))
    if not root.is_dir():
        return []
    result = []
    for film in sorted(root.iterdir()):
        if len(result) >= limit:
            break
        if not film.is_dir() or film.is_symlink() or not TAG.fullmatch(film.name):
            continue
        productions = ensure_local_root(film / "productions")
        if not productions.is_dir():
            continue
        for ep in sorted(productions.iterdir(), reverse=True):
            if len(result) >= limit:
                break
            if ep.is_symlink() or not ep.is_dir() or not TAG.fullmatch(ep.name):
                continue
            try:
                record = inspect(ep.name, film.name, film_root=root)
                has_render = (ep / "render-receipt.json").is_file()
                result.append({
                    "film_slug": film.name, "episode_id": ep.name,
                    "episode_sha256": record["episode_sha256"],
                    "shot_count": record["shot_count"],
                    "runtime_seconds": record["runtime_seconds"],
                    "state": "RENDER_RECEIPT_PRESENT_UNINSPECTED"
                             if has_render else "PREPARED_NOT_RENDERED",
                    "render_receipt_present_uninspected": has_render,
                    "visual_continuity_verified": False,
                })
            except (ValueError, OSError, PermissionError):
                result.append({"film_slug": film.name, "episode_id": ep.name,
                               "state": "INVALID_NEEDS_OWNER_REVIEW",
                               "render_receipt_present_uninspected": False})
    return result


def _wave_duration(path, total):
    ensure_local_root(path)
    if not path.is_file() or path.stat().st_size > 32_000_000:
        raise FilmProductionError("Missing/oversized local TTS WAV")
    try:
        with wave.open(str(path), "rb") as audio:
            if (audio.getcomptype() != "NONE" or audio.getsampwidth() != 2
                    or audio.getnchannels() not in (1, 2)
                    or not 8000 <= audio.getframerate() <= 48000):
                raise FilmProductionError("Only local 16-bit PCM WAV is allowed")
            seconds = audio.getnframes() / audio.getframerate()
            if not .3 < seconds <= total + .05:
                raise FilmProductionError("Narration exceeds episode duration")
            return round(seconds, 3)
    except (OSError, EOFError, wave.Error, ZeroDivisionError) as exc:
        raise FilmProductionError("Invalid local voiceover") from exc


def _voice_receipt(folder, plan_sha, duration):
    receipt = folder / "voiceover-receipt.json"
    wav = folder / "voiceover.wav"
    ensure_local_root(receipt)
    ensure_local_root(wav)
    if not receipt.is_file():
        if wav.exists():
            raise FilmProductionError("Untracked voiceover cannot be used")
        return None
    record = _signed(_read_json(receipt, 6000), "receipt_sha256")
    if (record.get("format") != VOICE_FORMAT or record.get("episode_sha256") != plan_sha
            or record.get("voice_sha256") != _file_hash(wav)
            or record.get("duration_seconds") != _wave_duration(wav, duration)
            or record.get("voice_language_verified") is not False):
        raise FilmProductionError("Voice provenance check failed")
    return record


def _file_hash(path):
    ensure_local_root(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def voice(episode_id, film_slug, episode_sha256, *, engine, voice_name=None,
          confirmed=False, film_root=FILMS):
    """Opt-in installed Windows/Piper TTS; NEVER downloads voices or revoices."""
    if confirmed is not True:
        raise PermissionError("Owner must approve local TTS engine execution")
    ops_control.require_active()
    plan = inspect(episode_id, film_slug, film_root=film_root)
    if _checksum(episode_sha256, "episode SHA") != plan["episode_sha256"]:
        raise PermissionError("Stale episode SHA")
    folder = _folder(film_slug, episode_id, film_root)
    if any((folder / file).exists() for file in (
            "voiceover.wav", "voiceover.partial.wav", "voiceover-receipt.json",
            "narration.txt", "render-receipt.json", "episode.mp4")):
        raise FileExistsError("Episode already contains voice, render or partial TTS")
    if voice_name is not None and (
            not isinstance(voice_name, str)
            or not media_render.VOICE_RE.fullmatch(voice_name)):
        raise FilmProductionError("Invalid TTS voice identifier")
    narration = folder / "narration.txt"
    pending = folder / "voiceover.partial.wav"
    narration.write_text(". ".join(s["caption"] for s in plan["shots"]), encoding="utf-8")
    committed = False
    try:
        cmd, stdin = media_render._voice_command(engine, folder, voice_name)
        media_render._run_process(cmd, cwd=folder, timeout=150, input_text=stdin)
        duration = _wave_duration(pending, _duration(plan["shot_count"]))
        output = folder / "voiceover.wav"
        pending.rename(output)
        body = {"format": VOICE_FORMAT, "episode_sha256": episode_sha256,
                "engine": engine, "voice_name": voice_name,
                "voice_sha256": _file_hash(output),
                "duration_seconds": duration, "voice_language_verified": False,
                "source": "owner_approved_offline_tts"}
        receipt = {**body, "receipt_sha256": _digest(body)}
        with (folder / "voiceover-receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
        committed = True
        return {"status": "LOCAL_TTS_CREATED_REVIEW_REQUIRED",
                "episode_id": episode_id, "voice_sha256": body["voice_sha256"],
                "voice_language_verified": False,
                "duration_seconds": duration, "receipt_sha256": receipt["receipt_sha256"]}
    finally:
        narration.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
        if not committed:
            (folder / "voiceover.wav").unlink(missing_ok=True)


def _run(args, timeout):
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise FilmProductionError("Install trusted FFmpeg on PATH")
    try:
        done = subprocess.run([executable, *args], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FilmProductionError("Local FFmpeg timed out/failed") from exc
    if done.returncode:
        raise FilmProductionError("Local FFmpeg assembly or decode failed")
    return done


def _probe_master(path, shot_count):
    """Re-probe the actual final MP4 (not a provider metadata success)."""
    raw = motion_verify._run("ffprobe", [
        "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate,nb_read_frames"
                         ":format=duration,format_name",
        "-of", "json", str(path)], seconds=45)
    audio = motion_verify._run("ffprobe", [
        "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "json",
        str(path)], seconds=30)
    try:
        data, sounds = json.loads(raw), json.loads(audio)
        video = data["streams"][0]
        soundtrack = sounds["streams"][0]
        frames = int(video["nb_read_frames"])
        secs = float(data["format"]["duration"])
        correct = (
            video["codec_name"] == "h264"
            and video["width"] == motion_comfy.PROFILE["width"]
            and video["height"] == motion_comfy.PROFILE["height"]
            and video["avg_frame_rate"] in {"12/1", "12"}
            and frames == shot_count * FRAMES_PER_SHOT
            and math.isfinite(secs)
            and abs(secs - _duration(shot_count)) < .3
            and soundtrack["codec_name"] == "aac"
            and "mp4" in data["format"]["format_name"]
        )
        if not correct:
            raise ValueError("Unexpected output video/audio")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise FilmProductionError("Final MP4 failed frame/duration/audio QA") from exc
    _run(["-hide_banner", "-nostdin", "-v", "error", "-xerror", "-threads", "2",
          "-i", str(path), "-map", "0:v:0", "-map", "0:a:0",
          "-f", "null", "-"], timeout=180)
    return {"codec": "h264", "width": video["width"], "height": video["height"],
            "frames_decoded": frames, "fps": FRAME_RATE,
            "duration_seconds": round(secs, 3), "audio_codec": "aac",
            "full_decode_pass": True}


def render(episode_id, film_slug, episode_sha256, *, confirmed=False,
           film_root=FILMS, db_path=DB):
    """One Owner-approved local FFmpeg run. No GPU inference, no overwrites."""
    if confirmed is not True:
        raise PermissionError("Owner must approve FFmpeg production run")
    ops_control.require_active()
    plan = inspect(episode_id, film_slug, film_root=film_root)
    if _checksum(episode_sha256, "episode SHA") != plan["episode_sha256"]:
        raise PermissionError("Episode SHA changed after Owner inspection")
    folder = _folder(film_slug, episode_id, film_root)
    final, pending = folder / "episode.mp4", folder / "episode.pending.mp4"
    srt, receipt = folder / "captions.srt", folder / "render-receipt.json"
    for f in (final, pending, srt, receipt):
        ensure_local_root(f)
        if f.exists():
            raise FileExistsError("Episode render already exists or needs manual cleanup")
    clips = _sources(plan["shots"], film_slug, plan["plan_sha"],
                     film_root, db_path)
    sound = _voice_receipt(folder, episode_sha256, _duration(plan["shot_count"]))
    voice_file = folder / "voiceover.wav"
    count = plan["shot_count"]
    captions = _srt(plan["shots"])
    # The script is only a *sidecar*. No untrusted text ever enters an FFmpeg
    # filter string, shell argument, binary path or download command.
    with srt.open("x", encoding="utf-8") as stream:
        stream.write(captions)
    committed = False
    try:
        cmd = ["-hide_banner", "-nostdin", "-v", "error", "-n"]
        for clip in clips:
            cmd.extend(["-i", str(clip)])
        if sound is not None:
            cmd.extend(["-i", str(voice_file)])
        else:
            cmd.extend(["-f", "lavfi", "-i",
                        "anullsrc=channel_layout=mono:sample_rate=16000"])
        nodes = []
        for index in range(count):
            nodes.append(f"[{index}:v:0]trim=start_frame=0:end_frame={FRAMES_PER_SHOT},"
                         "setpts=PTS-STARTPTS,setsar=1,fps=12,format=yuv420p"
                         f"[v{index}]")
        nodes.append("".join(f"[v{i}]" for i in range(count))
                     + f"concat=n={count}:v=1:a=0[outv]")
        cmd.extend([
            "-filter_complex", ";".join(nodes),
            "-map", "[outv]", "-map", f"{count}:a:0",
            "-af", "apad", "-t", f"{_duration(count):.6f}",
            "-r", "12", "-frames:v", str(count * FRAMES_PER_SHOT),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-threads", "2", "-c:a", "aac", "-b:a", "112k",
            "-movflags", "+faststart", "-f", "mp4", str(pending)])
        _run(cmd, timeout=540)
        if (not pending.is_file() or
                not MIN_MP4 <= pending.stat().st_size <= MAX_OUTPUT_BYTES):
            raise FilmProductionError("Missing or oversized assembled MP4")
        technical = _probe_master(pending, count)
        # Source clip SHA verification is repeated AFTER render to catch a
        # changed input during a long FFmpeg pass before committing output.
        _sources(plan["shots"], film_slug, plan["plan_sha"], film_root, db_path)
        if sound is not None:
            _voice_receipt(folder, episode_sha256, _duration(count))
        output_sha = _file_hash(pending)
        captions_sha = _file_hash(srt)
        body = {
            "format": OUTPUT_FORMAT, "episode_id": episode_id,
            "film_slug": film_slug, "episode_sha256": episode_sha256,
            "source_clips": [
                {"shot_id": x["shot_id"], "job_id": x["job_id"],
                 "clip_sha256": x["clip_sha256"],
                 "receipt_sha256": x["receipt_sha256"]}
                for x in plan["shots"]],
            "video_sha256": output_sha, "caption_sha256": captions_sha,
            "audio_sha256": None if sound is None else sound["voice_sha256"],
            "audio_kind": "silent" if sound is None else "owner_local_tts",
            "technical": technical, "status": READY,
            "visual_continuity_verified": False, "owner_watched": False,
            "audio_language_verified": False, "video_accepted": False,
            "published": False, "model_calls": 0,
        }
        report = {**body, "receipt_sha256": _digest(body)}
        pending.rename(final)
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        committed = True
        return {"film_slug": film_slug, "episode_id": episode_id,
                "status": READY, "video_sha256": output_sha,
                "caption_sha256": captions_sha, "receipt_sha256": report["receipt_sha256"],
                "duration_seconds": technical["duration_seconds"],
                "frames_decoded": technical["frames_decoded"],
                "audio_kind": body["audio_kind"], "visual_continuity_verified": False,
                "owner_watched": False, "video_accepted": False, "published": False}
    finally:
        pending.unlink(missing_ok=True)
        if not committed:
            # Only this invocation's output was written, never the input clips.
            final.unlink(missing_ok=True)
            srt.unlink(missing_ok=True)


def inspect_render(episode_id, film_slug, *, film_root=FILMS):
    plan = inspect(episode_id, film_slug, film_root=film_root)
    folder = _folder(film_slug, episode_id, film_root)
    report = _signed(_read_json(folder / "render-receipt.json"), "receipt_sha256")
    if (report.get("format") != OUTPUT_FORMAT
            or report.get("episode_sha256") != plan["episode_sha256"]
            or report.get("status") != READY
            or report.get("video_accepted") is not False
            or report.get("owner_watched") is not False
            or report.get("visual_continuity_verified") is not False
            or report.get("published") is not False
            or report.get("video_sha256") != _file_hash(folder / "episode.mp4")
            or report.get("caption_sha256") != _file_hash(folder / "captions.srt")):
        raise FilmProductionError("Rendered film receipt/file integrity mismatch")
    _voice_receipt(folder, plan["episode_sha256"], _duration(plan["shot_count"]))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Wave9 local film edit, no AI inference or publishing")
    cmd = parser.add_subparsers(dest="action", required=True)
    work = cmd.add_parser("draft")
    work.add_argument("--film-slug", required=True)
    work.add_argument("--episode-id", required=True)
    work.add_argument("--shot-count", type=int, required=True)
    work.add_argument("--first-shot", type=int, default=1)
    work.add_argument("--output", type=Path, required=True)
    prep = cmd.add_parser("prepare")
    prep.add_argument("--spec", type=Path, required=True)
    item = cmd.add_parser("inspect")
    item.add_argument("--film-slug", required=True)
    item.add_argument("--episode-id", required=True)
    cmd.add_parser("list")
    speech = cmd.add_parser("voice")
    speech.add_argument("--film-slug", required=True)
    speech.add_argument("--episode-id", required=True)
    speech.add_argument("--episode-sha", required=True)
    speech.add_argument("--engine", required=True, choices=["windows", "piper"])
    speech.add_argument("--voice-name")
    speech.add_argument("--confirm-tts", action="store_true")
    video = cmd.add_parser("render")
    video.add_argument("--film-slug", required=True)
    video.add_argument("--episode-id", required=True)
    video.add_argument("--episode-sha", required=True)
    video.add_argument("--confirm-ffmpeg", action="store_true")
    result = cmd.add_parser("receipt")
    result.add_argument("--film-slug", required=True)
    result.add_argument("--episode-id", required=True)
    args = parser.parse_args(argv)
    if args.action == "draft":
        document = draft(args.film_slug, args.episode_id,
                         shot_count=args.shot_count, first_shot=args.first_shot)
        ensure_local_root(args.output)
        if not args.output.parent.is_dir():
            raise FilmProductionError("Create the Owner draft output directory explicitly")
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
        outcome = {"status": "DRAFT_REQUIRES_OWNER_SHOT_NOTES",
                   "file": str(args.output), "shot_count": len(document["shots"]),
                   "model_calls": 0, "gpu_runs": 0}
    elif args.action == "prepare":
        document = _read_json(args.spec)
        outcome = prepare(document)
    elif args.action == "inspect":
        outcome = inspect(args.episode_id, args.film_slug)
    elif args.action == "list":
        outcome = {"episodes": list_episodes()}
    elif args.action == "voice":
        outcome = voice(
            args.episode_id, args.film_slug, args.episode_sha,
            engine=args.engine, voice_name=args.voice_name,
            confirmed=args.confirm_tts)
    elif args.action == "render":
        outcome = render(
            args.episode_id, args.film_slug, args.episode_sha,
            confirmed=args.confirm_ffmpeg)
    else:
        outcome = inspect_render(args.episode_id, args.film_slug)
    print(json.dumps(outcome, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
