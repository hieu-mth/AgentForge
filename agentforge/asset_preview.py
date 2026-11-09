"""Authenticated, bounded read-only preview of already imported AI image.

Never serves an arbitrary path: job ID comes from SQLite, asset name from
the fixed ComfyUI import ledger, content is verified against immutable SHA.
"""
import hashlib
from agentforge import image_studio_v24, web_assets

def image_for_job(job_id):
    row = image_studio_v24._row(job_id)
    if row["status"] not in ("ASSET_READY", "ATTACHED"):
        raise PermissionError("Image not ready for owner review")
    if not row["asset_name"] or not row["asset_sha"]:
        raise ValueError("Missing image receipt")
    contents, mime = web_assets.read_image(row["slug"], row["asset_name"])
    if len(contents) > 6 * 1024 * 1024 or hashlib.sha256(contents).hexdigest() != row["asset_sha"]:
        raise PermissionError("Image checksum mismatch")
    if mime != "image/png":
        raise ValueError("Only reviewed local PNG may be shown")
    return contents, mime
