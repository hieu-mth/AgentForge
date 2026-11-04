"""S2 media static quality and provenance checks; no network/execution.

ASSETS_PASS is not VIDEO_PASS. MP4 structural checks are not a full security
scanner or a substitute for watching/listening to the rendered clip.
"""
import re
import wave
from pathlib import Path

from agentforge import media_assets as assets

PHOTO_NAMES = re.compile(r"scene_[0-9]{2}\.png\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")


def _mp4_structural(path):
    """Read enough ISO-BMFF structure to require audio and video tracks."""
    size = path.stat().st_size
    if size < 512 or size > 160_000_000:
        raise assets.MediaError("MP4 outside allowed size range")
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
                raise assets.MediaError("MP4 box boundary invalid")
            box_types.add(name)
            if name == b"moov":
                if length > 2_000_000:
                    raise assets.MediaError("MP4 metadata too large")
                fd.seek(pos + header_size)
                moov = fd.read(length - header_size)
            pos += length
    if not {b"ftyp", b"moov", b"mdat"}.issubset(box_types):
        raise assets.MediaError("MP4 missing expected structural boxes")
    if b"vide" not in moov or b"soun" not in moov:
        raise assets.MediaError("MP4 missing video or audio track")
    return {"container": "mp4", "audio_track_present": True,
            "video_track_present": True, "structure_only": True}


def check(run_id):
    folder, manifest = assets.load_manifest(run_id)
    findings = []
    def fail(rule, message):
        findings.append({"rule": rule, "severity": "FAIL", "message": message})
    def warn(rule, message):
        findings.append({"rule": rule, "severity": "WARN", "message": message})

    try:
        scenes = assets._scenes(manifest.get("scenes"))
        assets._slug(manifest.get("slug"))
        if manifest.get("size") != list(assets.SIZE):
            raise assets.MediaError("Incorrect media dimensions")
        if manifest.get("duration_seconds") != sum(x["duration_seconds"] for x in scenes):
            raise assets.MediaError("Storyboard duration mismatch")
        if manifest.get("source_photo") and manifest.get("rights_attested") is not True:
            raise assets.MediaError("Unattested photo usage")
    except (KeyError, TypeError, assets.MediaError) as exc:
        fail("manifest", str(exc))
        scenes = []
    recorded = manifest.get("artifacts")
    if not isinstance(recorded, dict):
        fail("artifacts", "Invalid artifact records")
        recorded = {}
    expected = {f"scene_{index+1:02}.png" for index in range(len(scenes))}
    expected.update({"captions.srt", "ambient.wav"})
    if manifest.get("voiceover") is not None:
        expected.add("voiceover.wav")
    if manifest.get("video") is not None:
        expected.add("video.mp4")
    if set(recorded) != expected:
        fail("artifacts", "Artifact file list differs from declared storyboard")
    for filename in sorted(expected):
        if filename not in recorded:
            continue
        path = folder / filename
        try:
            assets._safe(path)
            if (not path.is_file() or not isinstance(recorded[filename], str)
                    or not SHA.fullmatch(recorded[filename])):
                raise assets.MediaError("Missing artifact or invalid checksum")
            if path.stat().st_size > 160_000_000:
                raise assets.MediaError("Asset exceeds size limit")
            if assets._sha(path) != recorded[filename]:
                raise assets.MediaError("Artifact fingerprint mismatch")
        except (OSError, assets.MediaError) as exc:
            fail("artifact_integrity", f"{filename}: {exc}")
            continue
        try:
            if PHOTO_NAMES.fullmatch(filename):
                from PIL import Image
                with Image.open(path) as image:
                    if image.format != "PNG" or image.size != assets.SIZE:
                        raise assets.MediaError("Unexpected media frame dimensions/format")
                    image.load()
            elif filename in {"ambient.wav", "voiceover.wav"}:
                with wave.open(str(path), "rb") as sound:
                    if (sound.getsampwidth() != 2 or sound.getnchannels() not in (1, 2)
                            or not 8000 <= sound.getframerate() <= 48000):
                        raise assets.MediaError("Unsupported WAV PCM format")
                    length = sound.getnframes() / sound.getframerate()
                    if filename == "ambient.wav" and abs(length - manifest["duration_seconds"]) > .02:
                        raise assets.MediaError("Ambient duration does not match storyboard")
                    if length < .3 or length > 180:
                        raise assets.MediaError("Audio duration outside allowed bounds")
            elif filename == "captions.srt":
                text = path.read_text(encoding="utf-8")
                if (text.count(" --> ") != len(scenes)
                        or not re.search(r"\A1\n00:00:00,000 --> ", text)
                        or not text.strip()):
                    raise assets.MediaError("SRT caption count/timing invalid")
            elif filename == "video.mp4":
                _mp4_structural(path)
        except (OSError, UnicodeError, EOFError, ValueError, assets.MediaError) as exc:
            fail("media_decode", f"{filename}: {type(exc).__name__}")
    if manifest.get("video") is not None:
        video = manifest["video"]
        if (not isinstance(video, dict) or video.get("file") != "video.mp4"
                or video.get("sha256") != recorded.get("video.mp4")
                or video.get("decoded_by_ffmpeg") is not True):
            fail("video_receipt", "Missing verified video receipt")
    if manifest.get("voiceover") is not None:
        voice = manifest["voiceover"]
        if (not isinstance(voice, dict) or voice.get("file") != "voiceover.wav"
                or voice.get("sha256") != recorded.get("voiceover.wav")):
            fail("voice_receipt", "Voiceover receipt invalid")
    if manifest.get("source_photo"):
        warn("photo_rights", "Owner attested source photo rights; license not independently verified")
    failures = sum(item["severity"] == "FAIL" for item in findings)
    warnings = sum(item["severity"] == "WARN" for item in findings)
    return {"run_id": run_id, "status": "FAIL" if failures else
            ("VIDEO_PASS" if manifest.get("video") is not None else "ASSETS_PASS"),
            "failures": failures, "warnings": warnings,
            "findings": findings, "image_count": len(scenes),
            "duration_seconds": manifest.get("duration_seconds"),
            "video_rendered": manifest.get("video") is not None,
            "video_verified": manifest.get("video") is not None and failures == 0,
            "security_verified": False, "published": False}


def edit_image(run_id, scene_index, operation):
    """Non-destructive Pillow edit of an S2-generated image."""
    if type(scene_index) is not int or not 1 <= scene_index <= 5:
        raise assets.MediaError("Invalid scene index")
    if operation not in {"warm", "cool", "contrast"}:
        raise assets.MediaError("Unsupported image operation")
    report = check(run_id)
    if report["failures"]:
        raise assets.MediaError("Source media quality failed")
    folder, manifest = assets.load_manifest(run_id)
    name = f"scene_{scene_index:02}.png"
    if name not in manifest["artifacts"]:
        raise assets.MediaError("Unknown scene")
    from PIL import Image, ImageEnhance
    from uuid import uuid4
    edited_folder = assets.OUTPUTS.parent / "media_edits" / run_id
    assets._safe(edited_folder)
    edited_folder.mkdir(parents=True, exist_ok=True)
    path = edited_folder / f"{uuid4().hex}.png"
    with Image.open(folder / name) as img:
        image = img.convert("RGB")
        if operation == "contrast":
            image = ImageEnhance.Contrast(image).enhance(1.23)
        else:
            overlay = Image.new("RGB", image.size, (237, 184, 113) if operation == "warm"
                                else (116, 170, 230))
            image = Image.blend(image, overlay, 0.13)
        with path.open("xb") as output:
            image.save(output, format="PNG")
    return {"run_id": run_id, "status": "EDIT_CREATED",
            "image_path": str(path), "sha256": assets._sha(path),
            "source_file": name, "operation": operation,
            "original_modified": False}
