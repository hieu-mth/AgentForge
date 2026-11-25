"""Opt-in LTX V2 pilot. One paid submission per durable request ID; no retries."""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing
from urllib.parse import urlsplit
from uuid import uuid4

from agentforge.paths import ensure_local_root
from agentforge.features.media import render

HOST = "api.ltx.io"
MODELS = {"ltx-2-3-fast", "ltx-2-3-pro"}
DURATIONS = (6, 8, 10)
MAX_MP4 = 160 * 1024 * 1024
DB_PATH = Path.home() / ".agentforge" / "ltx-pilot.sqlite3"


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid request or provider ID.")
    return value


def payload(model, prompt, duration, *, image=None, audio=True):
    if model not in MODELS or type(duration) is not int or duration not in DURATIONS:
        raise ValueError("Pilot supports explicitly selected LTX 2.3 models, 6/8/10 seconds.")
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 5000 or type(audio) is not bool:
        raise ValueError("Invalid prompt or audio setting.")
    result = {"model": model, "prompt": prompt, "duration": duration,
              "resolution": "1280x720", "fps": 24, "generate_audio": audio}
    if image is not None:
        from PIL import Image
        import io
        if not isinstance(image, bytes) or not 1 <= len(image) <= 4 * 1024 * 1024:
            raise ValueError("Pilot input image must be at most 4 MiB.")
        with Image.open(io.BytesIO(image)) as im:
            if im.format not in {"PNG", "JPEG"} or im.width * im.height > 12_000_000:
                raise ValueError("Unsupported image.")
            fmt = im.format.lower()
            im.verify()
        result["image_uri"] = "data:image/" + fmt + ";base64," + base64.b64encode(image).decode("ascii")
    return result


def _key():
    key = os.environ.get("LTX_API_KEY", "")
    if not re.fullmatch(r"[!-~]{1,4096}", key):
        raise ValueError("Set LTX_API_KEY in this terminal; never put it in a request file.")
    return key


def _request(method, path, key, body=None):
    conn = http.client.HTTPSConnection(HOST, timeout=30)
    try:
        conn.request(method, path, None if body is None else json.dumps(body).encode("utf-8"),
                     {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != (202 if method == "POST" else 200):
            raise ValueError("LTX HTTP " + str(resp.status))
        data = resp.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("LTX response too large.")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Invalid LTX response.")
        return result
    except (OSError, http.client.HTTPException, UnicodeError):
        raise ValueError("LTX transport failed; reconcile the existing request, do not resubmit.") from None
    finally:
        conn.close()


def _db():
    path = ensure_local_root(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, endpoint TEXT, model TEXT, "
                 "seconds INTEGER, request_sha TEXT, state TEXT, provider_id TEXT, output_sha TEXT)")
    conn.commit()
    return conn


def submit(request_id, body, *, max_seconds, confirmed=False):
    _id(request_id)
    if confirmed is not True or type(max_seconds) is not int or not 1 <= max_seconds <= 60:
        raise ValueError("Explicit paid request consent and lifetime pilot seconds cap required.")
    duration = body.get("duration")
    # Validate the canonical payload without accepting arbitrary provider fields.
    required = {"model", "prompt", "duration", "resolution", "fps", "generate_audio"}
    if set(body) not in (required, required | {"image_uri"}):
        raise ValueError("Unexpected request fields.")
    expected = payload(body["model"], body["prompt"], duration, audio=body["generate_audio"])
    if "image_uri" in body:
        match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", body["image_uri"])
        if not match or len(match[2]) > 6 * 1024 * 1024:
            raise ValueError("Invalid image URI.")
        expected = payload(body["model"], body["prompt"], duration, audio=body["generate_audio"],
                           image=base64.b64decode(match[2], validate=True))
    if body != expected:
        raise ValueError("Noncanonical pilot request.")
    key = _key()
    endpoint = "image-to-video" if "image_uri" in body else "text-to-video"
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    with closing(_db()) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM jobs WHERE id=?", (request_id,)).fetchone():
                raise ValueError("Request ID already reserved; poll it instead.")
            spent = db.execute("SELECT COALESCE(SUM(seconds),0) FROM jobs").fetchone()[0]
            if spent + duration > max_seconds:
                raise ValueError("Pilot seconds cap exceeded (all submissions including unknown count).")
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                       (request_id, endpoint, body["model"], duration, digest, "SUBMITTING", None, None))
        # Reservation is committed before the external side effect.
        response = _request("POST", "/v2/" + endpoint, key, body)
        remote_id = _id(response.get("id"))
        with db:
            db.execute("UPDATE jobs SET state='SUBMITTED',provider_id=? WHERE id=?", (remote_id, request_id))
    return {"id": request_id, "provider_id": remote_id, "state": "SUBMITTED", "reserved_seconds": duration}


def _download(url, target):
    u = urlsplit(url)
    if (u.scheme != "https" or u.netloc != "storage.googleapis.com" or not u.path or u.fragment):
        raise ValueError("Unexpected LTX download host; no credentials forwarded.")
    conn = http.client.HTTPSConnection(u.hostname, timeout=30)
    try:
        conn.request("GET", u.path + ("?" + u.query if u.query else ""))
        resp = conn.getresponse()
        if resp.status != 200:
            raise ValueError("LTX output download unavailable.")
        count = 0
        with target.open("xb") as f:
            while chunk := resp.read(1024 * 1024):
                count += len(chunk)
                if count > MAX_MP4:
                    raise ValueError("LTX output exceeds size limit.")
                f.write(chunk)
    except (OSError, http.client.HTTPException):
        raise ValueError("LTX output download failed.") from None
    finally:
        conn.close()


def _verify(path, seconds):
    if path.stat().st_size < 1024:
        raise ValueError("Incomplete MP4.")
    ffprobe = render.find_media_tool("ffprobe")
    if not ffprobe:
        raise ValueError("ffprobe required.")
    meta = render._run_process([ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate", "-of", "json", str(path)],
        cwd=path.parent, timeout=30)
    video = json.loads(meta.stdout)["streams"][0]
    if (video["width"], video["height"], video["avg_frame_rate"]) != (1280, 720, "24/1"):
        raise ValueError("LTX output does not match pilot profile.")
    decoded = render._run_process([render._ffmpeg(), "-nostdin", "-v", "error", "-xerror",
        "-i", str(path), "-map", "0:v:0", "-f", "null", "-", "-progress", "pipe:1"],
        cwd=path.parent, timeout=90)
    frames = re.findall(r"(?m)^frame=(\d+)", decoded.stdout)
    if not frames or int(frames[-1]) != seconds * 24:
        raise ValueError("LTX frame count differs from purchased duration.")
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def poll(request_id, output_dir):
    _id(request_id)
    with closing(_db()) as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (request_id,)).fetchone()
        if not row or row["state"] == "SUBMITTING":
            raise ValueError("Unknown submission; reconcile manually in LTX dashboard, never resubmit.")
        if row["state"] in {"FAILED", "VERIFIED"}:
            return dict(row)
        response = _request("GET", "/v2/" + row["endpoint"] + "/" + _id(row["provider_id"]), _key())
        if response.get("id") != row["provider_id"]:
            raise ValueError("LTX response ID mismatch.")
        state = response.get("status")
        if state in {"pending", "processing"}:
            return {"id": request_id, "state": state.upper()}
        if state == "failed":
            with db:
                db.execute("UPDATE jobs SET state='FAILED' WHERE id=?", (request_id,))
            return {"id": request_id, "state": "FAILED"}
        if state != "completed":
            raise ValueError("Unknown LTX status.")
        root = ensure_local_root(Path(output_dir))
        root.mkdir(parents=True, exist_ok=True)
        output = ensure_local_root(root / (request_id + ".mp4"))
        temp = ensure_local_root(root / (request_id + "." + uuid4().hex + ".part.mp4"))
        try:
            if output.exists():
                raise ValueError("Output already exists; inspect before further action.")
            _download(response["result"]["video_url"], temp)
            digest = _verify(temp, row["seconds"])
            # Exclusive output creation even if concurrent polling is attempted.
            with output.open("xb") as dest, temp.open("rb") as src:
                import shutil
                shutil.copyfileobj(src, dest)
            with db:
                db.execute("UPDATE jobs SET state='VERIFIED',output_sha=? WHERE id=?", (digest, request_id))
        finally:
            temp.unlink(missing_ok=True)
        return {"id": request_id, "state": "VERIFIED", "sha256": digest, "path": str(output),
                "creative_qa": "UNVERIFIED", "audio_qa": "UNVERIFIED"}


def main():
    parser = argparse.ArgumentParser(description="Explicit paid LTX V2 pilot (not Studio pipeline).")
    parser.add_argument("action", choices=["submit", "poll"])
    parser.add_argument("id", help="Owner-chosen stable 32-character lowercase hex ID")
    parser.add_argument("--model", choices=sorted(MODELS))
    parser.add_argument("--prompt")
    parser.add_argument("--seconds", type=int, choices=DURATIONS)
    parser.add_argument("--max-seconds", type=int)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--output", type=Path, default=Path.home() / ".agentforge" / "ltx-output")
    args = parser.parse_args()
    try:
        if args.action == "submit":
            image = None
            if args.image:
                path = ensure_local_root(args.image)
                with path.open("rb") as f:
                    image = f.read(4 * 1024 * 1024 + 1)
            result = submit(args.id, payload(args.model, args.prompt, args.seconds, image=image, audio=not args.silent),
                            max_seconds=args.max_seconds, confirmed=args.confirm_paid)
        else:
            result = poll(args.id, args.output)
        print(json.dumps(result))
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
        parser.exit(1, "LTX pilot failed. Inspect the existing request and billing; do not blindly resubmit.\n")


if __name__ == "__main__":
    main()
