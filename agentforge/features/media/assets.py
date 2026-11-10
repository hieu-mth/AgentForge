"""S2 local-first creative media asset generator: static frames, SRT, WAV.

No model, browser, network, subprocess, customer outreach or publication.
Produced files are immutable within a unique run directory.
"""
import hashlib
import json
import math
import re
import shutil
import struct
import unicodedata
import wave
from datetime import datetime, timezone
from pathlib import Path
from agentforge.paths import REPOSITORY_ROOT
from uuid import uuid4

ROOT = REPOSITORY_ROOT
OUTPUTS = ROOT / "workspace" / "media"
INPUTS = ROOT / "workspace" / "media_inputs"
SIZE = (540, 960)
RATE = 16000
SLUG_RE = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
RUN_RE = re.compile(r"[a-f0-9]{32}\Z")
PHOTO_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,49}\.(?:jpg|jpeg|png)\Z")


class MediaError(ValueError):
    pass


def _safe(path):
    for node in (path, *path.parents):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise MediaError("Symlink/junction media path refused")


def _slug(value):
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise MediaError("Invalid media slug")
    return value


def _run_id(value):
    if not isinstance(value, str) or not RUN_RE.fullmatch(value):
        raise MediaError("Invalid media run_id")
    return value


def _text(value, label, max_length):
    if not isinstance(value, str):
        raise MediaError(f"{label} must be text")
    value = unicodedata.normalize("NFC", value.strip())
    if not 1 <= len(value) <= max_length or any(
        ord(c) < 32 and c not in "\n\t" for c in value
    ):
        raise MediaError(f"Invalid {label} length or controls")
    return value


def _scenes(scenes):
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 5:
        raise MediaError("Expected 2-5 storyboard scenes")
    clean = []
    for item in scenes:
        if not isinstance(item, dict) or set(item) != {
            "headline", "caption", "duration_seconds"
        }:
            raise MediaError("Scenes require headline, caption and duration_seconds")
        duration = item["duration_seconds"]
        if type(duration) is not int or not 3 <= duration <= 8:
            raise MediaError("Scene duration must be an integer from 3 to 8 seconds")
        clean.append({
            "headline": _text(item["headline"], "headline", 68),
            "caption": _text(item["caption"], "caption", 180),
            "duration_seconds": duration,
        })
    if sum(s["duration_seconds"] for s in clean) > 35:
        raise MediaError("Storyboard exceeds 35 seconds")
    return clean


def _sha(path):
    """Hash local media without loading a potentially large MP4 into RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _font(size, bold=False):
    from PIL import ImageFont
    choices = ([
        "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ] if bold else [
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])
    for candidate in choices:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, max_width):
    words = text.replace("\n", " \n ").split()
    lines = []
    current = ""
    for word in words:
        if word == "\n":
            lines.append(current)
            current = ""
            continue
        probe = (current + " " + word).strip()
        if draw.textbbox((0, 0), probe, font=font)[2] <= max_width:
            current = probe
        else:
            if current:
                lines.append(current)
            current = word
            if draw.textbbox((0, 0), current, font=font)[2] > max_width:
                raise MediaError("Text contains a word too wide for layout")
    if current:
        lines.append(current)
    return lines


def _draw_lines(draw, text, font, *, x, y, width, fill, spacing, max_lines):
    lines = _wrap(draw, text, font, width)
    if len(lines) > max_lines:
        raise MediaError("Text overflows media frame; shorten the scene text")
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + spacing
    return y


def _photo_path(name, rights_confirmed):
    if name is None:
        return None
    if rights_confirmed is not True:
        raise PermissionError("Owner must attest rights to use the local photo")
    if not isinstance(name, str) or not PHOTO_RE.fullmatch(name):
        raise MediaError("Photo must be a simple .jpg/.jpeg/.png filename")
    source = INPUTS / name
    _safe(source)
    if not source.is_file() or not 0 < source.stat().st_size <= 12_000_000:
        raise MediaError("Approved photo not found or too large")
    return source


def validate_visual_plan(plan, scenes_count):
    """Allowlisted Owner visual choices; old storyboard runs remain classic."""
    if plan is None:
        return {"mode": "classic", "motion": "static", "image_job_ids": []}
    if not isinstance(plan, dict) or set(plan) != {"mode", "motion", "image_job_ids"}:
        raise MediaError("Invalid visual plan fields")
    mode, motion, ids = plan["mode"], plan["motion"], plan["image_job_ids"]
    if mode not in {"classic", "studio"} or motion not in {"static", "slow_zoom", "slow_pan"}:
        raise MediaError("Unsupported visual or motion mode")
    if not isinstance(ids, list):
        raise MediaError("Invalid studio image list")
    if mode == "classic":
        if ids:
            raise MediaError("Classic mode cannot silently include AI images")
    elif (len(ids) != scenes_count or len(set(str(x) for x in ids)) != len(ids)
          or any(not isinstance(x, str) or not RUN_RE.fullmatch(x) for x in ids)):
        raise MediaError("Studio mode requires one distinct verified image per scene")
    return {"mode": mode, "motion": motion, "image_job_ids": list(ids)}


def _studio_images(plan):
    """Reuse previously collected ComfyUI images; verify bytes and receipts.
    Never make an implicit model/GPU call or access arbitrary filesystem paths.
    """
    if plan["mode"] != "studio":
        return [], []
    from agentforge.asset_preview import image_for_job
    from PIL import Image
    import io
    images, receipts = [], []
    for job_id in plan["image_job_ids"]:
        contents, mime = image_for_job(job_id)
        with Image.open(io.BytesIO(contents)) as opened:
            if (mime != "image/png" or opened.format != "PNG"
                    or opened.width * opened.height > 18_000_000
                    or min(opened.size) < 256):
                raise MediaError("AI image has unsupported format or dimensions")
            opened.verify()
        images.append(contents)
        receipts.append({"job_id": job_id, "sha256": hashlib.sha256(contents).hexdigest()})
    return images, receipts


def render_studio_scene(path, scene, index, *, photo_bytes, title):
    """Portrait editorial composition with a distinct, verified photo per shot."""
    import io
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
    w, h = SIZE
    with Image.open(io.BytesIO(photo_bytes)) as opened:
        original = ImageOps.exif_transpose(opened.convert("RGB"))
        backdrop = ImageOps.fit(original, SIZE, method=Image.Resampling.LANCZOS)
        backdrop = backdrop.filter(ImageFilter.GaussianBlur(24))
        picture = Image.blend(backdrop, Image.new("RGB", SIZE, (9, 14, 22)), 0.42)
        # Preserve an entire landscape ComfyUI shot; portrait cropping could
        # otherwise remove the advertised product or main subject.
        hero = ImageOps.contain(original, (w-36, 460),
                                method=Image.Resampling.LANCZOS)
    picture.paste(hero, ((w-hero.width)//2, 55+(460-hero.height)//2))
    picture = picture.convert("RGBA")
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # Separate scene crops come from independent AI images rather than
    # recoloring a single static card.
    for y in range(410, h):
        alpha = round(226 * ((y - 410) / (h - 410)) ** 0.85)
        od.line((0, y, w, y), fill=(9, 14, 22, alpha))
    accent = [(235, 197, 146), (165, 215, 217), (244, 196, 181)][index % 3]
    od.rounded_rectangle((30, 578, 36, 825), radius=3, fill=accent)
    image = Image.alpha_composite(picture, overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.text((48, 565), f"SCENE {index+1:02}", font=_font(20, bold=True), fill=accent)
    headline = scene["headline"]
    head_font = _font(43, bold=True)
    while head_font.size > 29 and len(_wrap(draw, headline, head_font, w - 98)) > 3:
        head_font = _font(head_font.size - 2, bold=True)
    y = _draw_lines(draw, headline, head_font, x=48, y=622,
                    width=w-98, fill=(255, 255, 252), spacing=8, max_lines=3)
    body_font = _font(24)
    while body_font.size > 17 and (len(_wrap(draw, scene["caption"], body_font, w-98)) > 4
                                   or y + 18 + len(_wrap(draw, scene["caption"], body_font, w-98)) * (body_font.size + 6) > 900):
        body_font = _font(body_font.size - 1)
    _draw_lines(draw, scene["caption"], body_font, x=48, y=y+18,
                width=w-98, fill=(232, 234, 236), spacing=6, max_lines=5)
    image.save(path, format="PNG", optimize=True)


def render_scene(path, scene, index, *, photo=None, title="Creative Media"):
    """Rasterize a portrait card with Vietnamese copy; no remote image loads."""
    from PIL import Image, ImageDraw, ImageOps
    w, h = SIZE
    palettes = [
        ((27, 35, 51), (73, 55, 65), (238, 192, 146)),
        ((27, 43, 52), (41, 69, 68), (175, 222, 194)),
        ((43, 33, 44), (88, 59, 55), (240, 203, 161)),
    ]
    start, end, accent = palettes[index % len(palettes)]
    image = Image.new("RGB", SIZE)
    draw = ImageDraw.Draw(image)
    for y in range(h):
        t = y / max(1, h - 1)
        shade = tuple(round(a * (1-t) + b * t) for a, b in zip(start, end))
        draw.line((0, y, w, y), fill=shade)
    draw.ellipse((350, -55, 700, 310), outline=accent, width=5)
    draw.ellipse((-230, 680, 220, 1110), outline=accent, width=2)
    if photo is not None:
        with Image.open(photo) as opened:
            if opened.format not in {"JPEG", "PNG"} or getattr(opened, "is_animated", False):
                raise MediaError("Only static JPEG/PNG source photos are accepted")
            if opened.width * opened.height > 18_000_000:
                raise MediaError("Photo exceeds pixel budget")
            source = ImageOps.exif_transpose(opened.convert("RGB"))
            source = ImageOps.fit(source, (w-64, 346), method=Image.Resampling.LANCZOS)
        image.paste(source, (32, 100))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((32, 100, w-32, 446), radius=14, outline=accent, width=3)
    else:
        draw.rounded_rectangle((46, 135, w-46, 380), radius=28,
                               outline=accent, width=3)
        draw.ellipse((185, 185, 355, 325), outline=accent, width=5)
        draw.line((185, 255, 355, 255), fill=accent, width=3)
    font_head = _font(44, bold=True)
    font_body = _font(25)
    font_note = _font(19)
    head_y = _draw_lines(draw, scene["headline"], font_head,
                         x=46, y=505, width=w-92, fill=(255, 250, 239),
                         spacing=9, max_lines=3)
    body_y = max(head_y+20, 655)
    _draw_lines(draw, scene["caption"], font_body,
                x=46, y=body_y, width=w-92, fill=(231, 222, 212),
                spacing=9, max_lines=5)
    draw.rounded_rectangle((46, 856, w-46, 917), radius=16, fill=accent)
    footer = title
    while footer and draw.textbbox((0, 0), footer, font=font_note)[2] > w - 140:
        footer = footer[:-2]
    if footer != title:
        footer = footer.rstrip() + "…"
    draw.text((64, 873), footer, font=font_note, fill=(27, 35, 51))
    image.save(path, format="PNG", optimize=True)


def caption_text(scenes):
    """Deterministic SRT body used by generation AND independent QA."""
    elapsed = 0
    entries = []
    def timestamp(seconds):
        ms = int(seconds * 1000)
        return f"{ms//3600000:02}:{(ms//60000)%60:02}:{(ms//1000)%60:02},{ms%1000:03}"
    for index, scene in enumerate(scenes, 1):
        end = elapsed + scene["duration_seconds"]
        entries.append(f"{index}\n{timestamp(elapsed)} --> {timestamp(end)}\n"
                       f"{scene['caption']}\n")
        elapsed = end
    return "\n".join(entries) + "\n"


def write_captions(path, scenes):
    path.write_text(caption_text(scenes), encoding="utf-8")


def write_ambient(path, seconds):
    """Original soft oscillator bed, not a synthesized voice or licensed song."""
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        chunk = bytearray()
        count = seconds * RATE
        for i in range(count):
            t = i / RATE
            fade = min(1, t/0.55, (seconds-t)/0.75)
            sample = int(32767 * max(0, fade) * 0.037 * (
                0.60 * math.sin(2*math.pi*196*t) +
                0.29 * math.sin(2*math.pi*246.94*t) +
                0.11 * math.sin(2*math.pi*293.66*t)))
            chunk.extend(struct.pack("<h", sample))
            if len(chunk) >= 32000:
                out.writeframes(chunk)
                chunk.clear()
        if chunk:
            out.writeframes(chunk)


def folder_for(run_id):
    run_id = _run_id(run_id)
    path = OUTPUTS / run_id
    _safe(path)
    if not path.is_dir():
        raise MediaError("Media run not found")
    return path


def load_manifest(run_id):
    folder = folder_for(run_id)
    manifest = folder / "manifest.json"
    _safe(manifest)
    if not manifest.is_file() or manifest.stat().st_size > 16000:
        raise MediaError("Missing or oversized media manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("run_id") != run_id
            or data.get("schema_version") != 1):
        raise MediaError("Media manifest/run ID mismatch")
    return folder, data


def make_assets(payload):
    """Create immutable PNG/SRT/WAV artifacts in one exclusive media run."""
    if not isinstance(payload, dict) or set(payload) - {
        "slug", "title", "scenes", "photo_name", "rights_confirmed", "visual_plan"
    }:
        raise MediaError("Unexpected media request fields")
    slug = _slug(payload.get("slug"))
    title = _text(payload.get("title"), "project title", 88)
    scenes = _scenes(payload.get("scenes"))
    visual_plan = validate_visual_plan(payload.get("visual_plan"), len(scenes))
    if visual_plan["mode"] == "studio" and payload.get("photo_name") is not None:
        raise MediaError("Use either verified studio images or owner photo")
    photo = _photo_path(payload.get("photo_name"), payload.get("rights_confirmed"))
    studio_images, studio_receipts = _studio_images(visual_plan)
    _safe(OUTPUTS)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    stage = OUTPUTS / (".stage-" + run_id)
    final = OUTPUTS / run_id
    _safe(stage)
    stage.mkdir(exist_ok=False)
    try:
        names = []
        for index, scene in enumerate(scenes):
            name = f"scene_{index+1:02}.png"
            if visual_plan["mode"] == "studio":
                render_studio_scene(stage / name, scene, index,
                                    photo_bytes=studio_images[index], title=title)
            else:
                render_scene(stage / name, scene, index, photo=photo, title=title)
            names.append(name)
        write_captions(stage / "captions.srt", scenes)
        duration = sum(x["duration_seconds"] for x in scenes)
        write_ambient(stage / "ambient.wav", duration)
        assets = {name: _sha(stage / name)
                  for name in [*names, "captions.srt", "ambient.wav"]}
        metadata = {
            "schema_version": 1, "run_id": run_id, "slug": slug,
            "title": title, "scenes": scenes,
            "duration_seconds": duration, "size": list(SIZE),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_photo": photo.name if photo else None,
            "visual_plan": visual_plan,
            "studio_image_receipts": studio_receipts,
            "rights_attested": payload.get("rights_confirmed") is True if photo else None,
            "artifacts": assets, "video": None, "voiceover": None,
            "stage": "ASSETS_READY", "published": False,
            "revenue_verified": False, "security_verified": False,
        }
        (stage / "manifest.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8")
        if final.exists():
            raise FileExistsError("Media run already exists")
        stage.rename(final)
    except BaseException:
        # Delete ONLY this tool's own random staging folder, not existing data.
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return {"run_id": run_id, "project_slug": slug, "status": "ASSETS_READY",
            "project_path": str(final), "duration_seconds": duration,
            "image_count": len(names), "caption_path": str(final / "captions.srt"),
            "audio_path": str(final / "ambient.wav"), "video_rendered": False}
