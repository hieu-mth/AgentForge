"""Owner-gated local AI raster generation using ComfyUI (optional dependency).

This is an *adapter*, not a bundled image model. ComfyUI must be installed
separately at 127.0.0.1:8188 and a trusted standard checkpoint selected.
Uses only a fixed node allowlist and no arbitrary workflow/file execution.
Network dispatch is one-shot; ambiguous failures are never retried.
"""
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from agentforge import ops_control, product_builder, web_assets
from agentforge.integrations import comfyui as _comfyui

BASE = "http://127.0.0.1:8188"
DB = product_builder.ROOT / "data" / "company" / "image_studio_v24.sqlite3"
CHECKPOINT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.(?:safetensors|ckpt)\Z")
IMAGE_FILE = re.compile(r"af_[a-f0-9]{32}_[a-zA-Z0-9_.-]{1,80}\.png\Z")
HEX = re.compile(r"[a-f0-9]{64}\Z")
MAX_IMAGE = 6 * 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value):
    return product_builder._check_proposal_id(value)


def _path(value):
    target = Path(value) if value is not None else DB
    product_builder._check_path_chain(target)
    return target


def _connect(db_path=None, *, create=False):
    target = _path(db_path)
    if not create and not target.is_file():
        return None
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
        _path(target.parent)
    db = sqlite3.connect(target, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=20000")
    if create:
        db.execute("""CREATE TABLE IF NOT EXISTS jobs(
            job_id TEXT PRIMARY KEY, slug TEXT NOT NULL,
            status TEXT NOT NULL, prompt_sha TEXT NOT NULL,
            checkpoint TEXT NOT NULL, provider_id TEXT UNIQUE,
            asset_name TEXT, asset_sha TEXT, source_html_sha TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        db.commit()
    return db


def _request(path, *, payload=None, max_bytes=262144, timeout=5, opener=None):
    """Use fixed-loopback transport. Injected opener is only a test seam."""
    _comfyui.validate_image_route(path, has_body=payload is not None)
    if opener is None:
        return _comfyui.request_image_bytes(
            path, body=payload, timeout=timeout, max_response_bytes=max_bytes)
    # Preserve existing deterministic fixture seam while applying the same
    # strict path/response checks before any response is parsed.
    data = None if payload is None else json.dumps(
        payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="GET" if data is None else "POST")
    with opener(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("Local ComfyUI returned non-success status")
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Local image response exceeds size limit")
    return raw


def health(*, opener=None):
    """Read-only checkpoint discovery, never submits an image model job."""
    try:
        data = json.loads(_request("/models/checkpoints", opener=opener, timeout=3))
        if not isinstance(data, list):
            raise ValueError("Invalid checkpoint response")
        models = sorted({x for x in data if isinstance(x, str) and CHECKPOINT.fullmatch(x)})
        return {"status": "READY" if models else "NO_CHECKPOINT",
                "checkpoints": models[:32], "truncated": len(models) > 32,
                "generation_invoked": False}
    except (OSError, RuntimeError, ValueError, TypeError, urllib.error.URLError):
        return {"status": "UNAVAILABLE", "checkpoints": [],
                "generation_invoked": False}


def _workflow(job_id, prompt, checkpoint):
    """Trusted core ComfyUI node graph; no custom nodes/remote workflows."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "watermark, text, fake logo, duplicate furniture, distorted bed",
                         "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 768, "height": 512, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": secrets.randbelow(2**32), "steps": 20,
                         "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal",
                         "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0],
                         "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "af_" + job_id, "images": ["6", 0]}},
    }


def _row(job_id, *, db_path=None):
    job_id = _id(job_id)
    db = _connect(db_path)
    if db is None:
        raise KeyError("Image job not found")
    with closing(db):
        row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise KeyError("Image job not found")
    return dict(row)


def submit(slug, prompt, checkpoint, *, confirm_generation=False, db_path=None,
           opener=None):
    if confirm_generation is not True:
        raise PermissionError("Owner confirmation required for GPU image generation")
    ops_control.require_active()
    web_assets._project(slug)  # Requires an owner-applied local website.
    if (not isinstance(prompt, str) or not 20 <= len(prompt.strip()) <= 450
            or any(ord(ch) < 32 and ch not in "\n\t" for ch in prompt)):
        raise ValueError("Image description must be 20–450 safe characters")
    if not isinstance(checkpoint, str) or not CHECKPOINT.fullmatch(checkpoint):
        raise ValueError("Unsupported checkpoint file name")
    availability = health(opener=opener)
    if availability["status"] != "READY" or checkpoint not in availability["checkpoints"]:
        raise PermissionError("Selected checkpoint not available on local ComfyUI")
    jobs = web_assets.list_images(slug)
    if len(jobs) >= web_assets.MAX_IMAGES:
        raise PermissionError("Project image limit reached")
    job_id, now = uuid4().hex, _now()
    sha = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()
    with closing(_connect(db_path, create=True)) as db, db:
        db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, slug, "SUBMITTING", sha, checkpoint, None,
                    None, None, None, now, now))
    # SUBMITTING stays visible after an uncertain HTTP failure. Never replay.
    raw = _request("/prompt", payload={"prompt": _workflow(job_id, prompt.strip(), checkpoint)},
                   max_bytes=65536, timeout=12, opener=opener)
    response = json.loads(raw)
    provider_id = str(UUID(response["prompt_id"]))
    with closing(_connect(db_path, create=True)) as db, db:
        updated = db.execute("""UPDATE jobs SET status='SUBMITTED',
            provider_id=?,updated_at=? WHERE job_id=? AND status='SUBMITTING'""",
            (provider_id, _now(), job_id))
        if updated.rowcount != 1:
            raise RuntimeError("Image dispatch ledger changed")
    return {"job_id": job_id, "status": "SUBMITTED",
            "provider": "LOCAL_COMFYUI", "model_calls": 0,
            "external_publication": False, "requires_owner_image_review": True}


def _history(row, *, opener=None):
    raw = _request("/history/" + row["provider_id"], max_bytes=131072,
                   timeout=5, opener=opener)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid ComfyUI history")
    return data.get(row["provider_id"])


def collect(job_id, *, confirm_import=False, db_path=None, opener=None):
    if confirm_import is not True:
        raise PermissionError("Explicit owner approval to import image required")
    ops_control.require_active()
    row = _row(job_id, db_path=db_path)
    if row["status"] != "SUBMITTED":
        raise PermissionError("Only submitted images may be imported once")
    record = _history(row, opener=opener)
    if record is None:
        return {"job_id": job_id, "status": "PROCESSING", "imported": False}
    if (not isinstance(record, dict) or not isinstance(record.get("status"), dict)
            or record["status"].get("status_str") != "success"
            or record["status"].get("completed") is not True):
        raise PermissionError("Image generation failed or is not complete")
    results = record.get("outputs", {}).get("7", {}).get("images", [])
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError("Expected exactly one ComfyUI output image")
    item = results[0]
    if (not isinstance(item, dict) or item.get("subfolder") != ""
            or item.get("type") != "output" or
            not isinstance(item.get("filename"), str) or
            not IMAGE_FILE.fullmatch(item["filename"]) or
            not item["filename"].startswith("af_" + job_id + "_")):
        raise PermissionError("Untrusted output image filename")
    with closing(_connect(db_path, create=True)) as db, db:
        updated = db.execute("""UPDATE jobs SET status='COLLECTING',updated_at=?
            WHERE job_id=? AND status='SUBMITTED'""", (_now(), job_id))
        if updated.rowcount != 1:
            raise PermissionError("Image import already claimed")
    qs = urllib.parse.urlencode({"filename": item["filename"],
                                "subfolder": "", "type": "output"})
    contents = _request("/view?" + qs, max_bytes=MAX_IMAGE,
                        timeout=15, opener=opener)
    if not web_assets._format(contents, "png"):
        raise ValueError("ComfyUI did not return a PNG")
    from PIL import Image  # Optional [media] dependency, only needed for image import.
    with Image.open(io.BytesIO(contents)) as image:
        if image.format != "PNG" or not (256 <= image.width <= 2048
                                        and 256 <= image.height <= 2048):
            raise ValueError("Invalid generated image dimensions")
        image.verify()
    image_name = "af-ai-" + job_id + ".png"
    target = web_assets._path(row["slug"], image_name)
    files = web_assets.list_images(row["slug"])
    if (len(files) >= web_assets.MAX_IMAGES or
            sum(x["bytes"] for x in files) + len(contents) > web_assets.MAX_ALL_BYTES):
        raise PermissionError("Image asset budget exceeded")
    target.parent.mkdir(parents=True, exist_ok=True)
    product_builder._check_path_chain(target)
    with target.open("xb") as out:
        out.write(contents)
        out.flush()
        os.fsync(out.fileno())
    digest = hashlib.sha256(contents).hexdigest()
    with closing(_connect(db_path, create=True)) as db, db:
        updated = db.execute("""UPDATE jobs SET status='ASSET_READY',
            asset_name=?,asset_sha=?,updated_at=?
            WHERE job_id=? AND status='COLLECTING'""",
            (image_name, digest, _now(), job_id))
        if updated.rowcount != 1:
            raise RuntimeError("Image import ledger changed")
    return {"job_id": job_id, "status": "ASSET_READY",
            "asset": "assets/" + image_name, "sha256": digest,
            "owner_review_required": True, "published": False}


def attach(job_id, image_sha, html_sha, *, confirm_attach=False, db_path=None):
    """Owner-reviewed SHA-bound attachment; backup original HTML; never publish."""
    if confirm_attach is not True:
        raise PermissionError("Explicit owner approval required to attach AI image")
    ops_control.require_active()
    row = _row(job_id, db_path=db_path)
    if (row["status"] != "ASSET_READY" or not isinstance(image_sha, str)
            or image_sha != row["asset_sha"] or
            not isinstance(html_sha, str) or not HEX.fullmatch(html_sha)):
        raise PermissionError("Image not reviewed or SHA changed")
    contents, _ = web_assets.read_image(row["slug"], row["asset_name"])
    if hashlib.sha256(contents).hexdigest() != image_sha:
        raise PermissionError("Image has changed")
    project = web_assets._project(row["slug"])
    original = project / "index.html"
    product_builder._check_path_chain(original)
    before = original.read_bytes()
    if hashlib.sha256(before).hexdigest() != html_sha:
        raise PermissionError("Website source has changed")
    text = before.decode("utf-8")
    figure = ('<figure class="af-ai-hero">'
              '<img src="assets/' + row["asset_name"] +
              '" alt="Minh họa phòng ngủ do AI tạo, không phải ảnh sản phẩm thực tế">'
              '<figcaption>Minh họa AI, không đại diện cho mẫu nệm đang bán.</figcaption>'
              '</figure>')
    style = ('<style id="af-ai-hero-style">'
             '.af-ai-hero{max-width:960px;margin:24px auto;overflow:hidden;'
             'border-radius:22px;background:#eee5dc}'
             '.af-ai-hero img{width:100%;height:auto;display:block;object-fit:cover}'
             '.af-ai-hero figcaption{font-size:12px;padding:8px 14px;color:#62564b}'
             '</style>')
    import re
    if not re.search(r"(?i)</head\s*>", text) or not re.search(r"(?i)<main(?:\s|>)", text):
        raise ValueError("Website needs a normal head and main element")
    amended = re.sub(r"(?i)</head\s*>", style + "</head>", text, count=1)
    amended = re.sub(r"(?i)(<main(?:\s[^>]*)?>)",
                     lambda m: m.group(1) + figure, amended, count=1)
    product_builder._validate_files({
        "summary": "AI image attached for owner review",
        "files": [{"path": "index.html", "content": amended}]})
    product_builder._require_static_quality(amended)
    web_assets.verify_references(row["slug"], amended)
    with closing(_connect(db_path, create=True)) as db, db:
        updated = db.execute("""UPDATE jobs SET status='ATTACHING',
            source_html_sha=?,updated_at=? WHERE job_id=? AND status='ASSET_READY'""",
            (html_sha, _now(), job_id))
        if updated.rowcount != 1:
            raise PermissionError("Image already attached or claimed")
    backup = project / ".backups"
    product_builder._check_path_chain(backup)
    backup.mkdir(exist_ok=True)
    backup_path = backup / (job_id + "-index.html")
    product_builder._check_path_chain(backup_path)
    with backup_path.open("xb") as out:
        out.write(before)
        out.flush()
        os.fsync(out.fileno())
    temp = project / (".image-attach-" + job_id + ".tmp")
    product_builder._check_path_chain(temp)
    with temp.open("xb") as out:
        out.write(amended.encode("utf-8"))
        out.flush()
        os.fsync(out.fileno())
    # Last identity check before replacement: fail closed on changes.
    if original.read_bytes() != before:
        raise RuntimeError("Website modified during image attach")
    os.replace(temp, original)
    with closing(_connect(db_path, create=True)) as db, db:
        updated = db.execute("""UPDATE jobs SET status='ATTACHED',updated_at=?
            WHERE job_id=? AND status='ATTACHING'""", (_now(), job_id))
        if updated.rowcount != 1:
            raise RuntimeError("Image attach ledger changed")
    return {"job_id": job_id, "status": "ATTACHED", "published": False,
            "backup": ".backups/" + backup_path.name,
            "html_sha256": hashlib.sha256(amended.encode("utf-8")).hexdigest()}


def report(*, db_path=None):
    db = _connect(db_path)
    if db is None:
        return {"jobs": [], "provider": "LOCAL_COMFYUI"}
    with closing(db):
        rows = [dict(x) for x in db.execute("""SELECT job_id,slug,status,checkpoint,
                  provider_id,asset_name,asset_sha,source_html_sha,created_at,updated_at
                  FROM jobs ORDER BY created_at DESC LIMIT 25""")]
    for row in rows:
        try:
            path = web_assets._project(row["slug"]) / "index.html"
            product_builder._check_path_chain(path)
            row["current_html_sha"] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError):
            row["current_html_sha"] = None
    return {"jobs": rows, "provider": "LOCAL_COMFYUI",
            "automatic_retry": False, "published": False}
