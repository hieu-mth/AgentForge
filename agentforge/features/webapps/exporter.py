"""Deterministic source-only React exports from exact SHA-reviewed proposals.

ZIP includes a bounded manifest and *only* the files verified by the provider.
It never runs source, npm, model, Docker or network requests. Export is not
deployment/build certification. No workspace/source proposal is modified.
"""
import hashlib
import io
import json
import zipfile

from agentforge import webapp_builder, webapp_developer

MANIFEST_NAME = "agentforge-export-manifest.json"
FORMAT = "agentforge.webapp.export.v1"
ZIP_LIMIT = 240_000
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _entry(archive, name, raw):
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def create_zip(proposal_id, sha256):
    provider = webapp_developer.provider(proposal_id)
    doc, _ = provider._read_proposal(proposal_id)
    if doc["sha256"] != sha256:
        raise PermissionError("EXPORT_SOURCE_STALE")
    slug = doc["project_slug"]  # Strictly validated by signed provider.
    files = sorted(doc["files"], key=lambda item: item["path"])
    # Files are a trusted, bounded provider allowlist, not user-supplied paths.
    parts = []
    manifest_files = []
    total = 0
    for file in files:
        name = file["path"]
        if (not isinstance(name, str) or name.startswith("/")
                or name.startswith(".") or "\\" in name
                or any(part in {"", ".", ".."} for part in name.split("/"))):
            raise ValueError("EXPORT_INVALID_PATH")
        content = file["content"].encode("utf-8")
        total += len(content)
        parts.append((slug + "/" + name, content))
        manifest_files.append({"path": name, "sha256": _sha(content),
                               "bytes": len(content)})
    if not 1 <= len(parts) <= 30 or total > 160_000:
        raise ValueError("EXPORT_INVALID_SIZE")
    manifest = {"format": FORMAT, "proposal_id": proposal_id,
                "source_sha256": sha256, "project_slug": slug,
                "files": manifest_files,
                "build_verified": False, "browser_verified": False,
                "deployment_authorized": False}
    body = json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        _entry(archive, MANIFEST_NAME, body)
        for name, raw in parts:
            _entry(archive, name, raw)
    raw = stream.getvalue()
    if len(raw) > ZIP_LIMIT:
        raise ValueError("EXPORT_INVALID_SIZE")
    return {"data": raw, "zip_sha256": _sha(raw), "source_sha256": sha256,
            "filename": "agentforge-" + slug + "-" + sha256[:12] + ".zip",
            "file_count": len(parts), "manifest": manifest}


def verify_zip(archive, proposal_id, sha256):
    """Byte-for-byte deterministic comparison to the signed local source."""
    if not isinstance(archive, bytes) or len(archive) > ZIP_LIMIT:
        raise ValueError("EXPORT_INVALID_SIZE")
    expected = create_zip(proposal_id, sha256)
    if _sha(archive) != expected["zip_sha256"] or archive != expected["data"]:
        raise PermissionError("EXPORT_INTEGRITY_FAILED")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        if bundle.namelist() != ([MANIFEST_NAME] + [
                expected["manifest"]["project_slug"] + "/" + f["path"]
                for f in expected["manifest"]["files"]]):
            raise ValueError("EXPORT_INVALID_FILES")
        actual = json.loads(bundle.read(MANIFEST_NAME).decode("utf-8"))
    if actual != expected["manifest"]:
        raise ValueError("EXPORT_INVALID_MANIFEST")
    return {"status": "VERIFIED_SOURCE_ONLY",
            "zip_sha256": expected["zip_sha256"],
            "source_sha256": sha256,
            "file_count": expected["file_count"],
            "build_verified": False, "browser_verified": False,
            "deployment_authorized": False}
