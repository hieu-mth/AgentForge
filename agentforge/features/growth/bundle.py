"""S5 channel-specific, owner-approved *offline handoff* packages.

This DOES NOT call YouTube or TikTok, create accounts or publish.
No credentials, outbound requests or fake upload receipts are involved.
"""
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge.features.growth import store
from agentforge import media_assets, media_quality

OUT = store.ROOT / "workspace" / "growth" / "packages"


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def prepare(campaign, channel, run_id, title, description, *,
            confirm_rights=False, confirm_write=False, db_path=None):
    if confirm_write is not True or confirm_rights is not True:
        raise PermissionError("Owner must approve content handoff and rights")
    info = store.campaign_info(campaign, db_path=db_path)
    if channel not in {"youtube", "tiktok"}:
        raise store.GrowthError("Only supported manual YouTube/TikTok handoffs")
    title = store._text(title, max_length=100, field="post title")
    description = store._text(description, max_length=1200, field="description")
    folder, manifest = media_assets.load_manifest(run_id)
    report = media_quality.check(run_id)
    if (report["status"] != "VIDEO_PASS" or report["failures"] != 0 or
            not report["video_verified"]):
        raise store.GrowthError("Video must pass existing S2 media quality check")
    if manifest.get("duration_seconds", 999) > 180:
        raise store.GrowthError("Video exceeds conservative short-video duration")
    if manifest.get("size") != [540, 960]:
        raise store.GrowthError("Only portrait generated video may be packed")
    if manifest.get("source_photo") and manifest.get("rights_attested") is not True:
        raise store.GrowthError("Source media rights not attested")
    for name in ("video.mp4", "captions.srt"):
        path = folder / name
        media_assets._safe(path)
        if not path.is_file() or _sha(path) != manifest["artifacts"].get(name):
            raise store.GrowthError("Media source changed since S2 QA")
    store._safe(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    bundle_name = uuid4().hex + ".zip"
    stage, final = OUT / (bundle_name + ".part"), OUT / bundle_name
    store._safe(stage)
    store._safe(final)
    if stage.exists() or final.exists():
        raise FileExistsError("Bundle output already exists")
    receipt = {
        "schema_version": 1, "campaign": campaign, "channel": channel,
        "media_run_id": run_id, "synthetic": bool(info["synthetic"]),
        "title": title, "description": description,
        "video_sha256": manifest["artifacts"]["video.mp4"],
        "captions_sha256": manifest["artifacts"]["captions.srt"],
        "rights_owner_attested": True,
        "publication_status": "NOT_PUBLISHED",
        "platform_api_used": False, "external_publication_verified": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with zipfile.ZipFile(stage, mode="x") as zf:
            zf.write(folder / "video.mp4", arcname="video.mp4",
                     compress_type=zipfile.ZIP_STORED)
            zf.write(folder / "captions.srt", arcname="captions.srt",
                     compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("post.txt", title + "\n\n" + description + "\n")
            zf.writestr("manifest.json", json.dumps(
                receipt, ensure_ascii=False, indent=2, allow_nan=False))
        if stage.stat().st_size > 165_000_000:
            raise store.GrowthError("Bundle exceeds allowed size")
        with zipfile.ZipFile(stage) as zf:
            if (set(zf.namelist()) != {"video.mp4", "captions.srt",
                                       "post.txt", "manifest.json"}
                    or zf.testzip() is not None):
                raise store.GrowthError("Bundle verification failed")
        stage.rename(final)
        saved = store.save_package(
            campaign, channel, run_id, final, _sha(final),
            manifest["artifacts"]["video.mp4"], db_path=db_path)
    except BaseException:
        # Only clean files newly created by this invocation.
        stage.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        raise
    return {
        **saved, "source_video_sha256": manifest["artifacts"]["video.mp4"],
        "requires_manual_platform_upload": True,
        "owner_review_required": True, "synthetic": bool(info["synthetic"]),
        "channel_account_connected": False,
    }
