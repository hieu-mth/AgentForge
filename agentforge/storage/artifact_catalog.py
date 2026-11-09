"""Bounded read-only inventory of AgentForge-owned local artifacts.

Never follows symlinks or Windows junctions. Never serves file contents, executes
code, deletes assets, or mistakes drafts for deployed products.
"""
from pathlib import Path

from agentforge import media_assets, product_builder

LIMIT = 40


def _safe(path):
    product_builder._check_path_chain(path)


def _children(folder):
    _safe(folder)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ValueError("Artifact root must be a directory")
    return sorted(folder.iterdir(), key=lambda p: p.name)


def report(*, products=None, proposals=None, media=None, limit=LIMIT):
    if type(limit) is not int or not 1 <= limit <= LIMIT:
        raise ValueError("Inventory limit must be 1..40")
    products = Path(products) if products is not None else product_builder.PRODUCTS
    proposals = Path(proposals) if proposals is not None else product_builder.PROPOSALS
    media = Path(media) if media is not None else media_assets.OUTPUTS
    items = []
    for folder in _children(products):
        _safe(folder)
        if not folder.is_dir():
            continue
        try:
            slug = product_builder._check_slug(folder.name)
            html = folder / "index.html"
            _safe(html)
            if not html.is_file():
                continue
            size = html.stat().st_size
        except (ValueError, OSError):
            continue
        items.append({"kind": "website", "id": slug, "status": "LOCAL_FILES_ONLY",
                      "files": 1, "bytes": size, "deployed": False})
    for path in _children(proposals):
        _safe(path)
        if not path.is_file() or path.suffix != ".json":
            continue
        try:
            product_builder._check_proposal_id(path.stem)
            size = path.stat().st_size
            if size > product_builder.MAX_PROPOSAL_BYTES or size < 1:
                continue
        except (ValueError, OSError):
            continue
        items.append({"kind": "proposal", "id": path.stem,
                      "status": "REVIEW_REQUIRED", "files": 1, "bytes": size,
                      "deployed": False})
    for folder in _children(media):
        _safe(folder)
        if not folder.is_dir():
            continue
        try:
            media_assets._run_id(folder.name)
            manifest = folder / "manifest.json"
            _safe(manifest)
            if not manifest.is_file() or not 0 < manifest.stat().st_size <= 16000:
                continue
            size = manifest.stat().st_size
        except (ValueError, OSError):
            continue
        items.append({"kind": "media", "id": folder.name,
                      "status": "LOCAL_MEDIA", "files": 1, "bytes": size,
                      "deployed": False})
    items.sort(key=lambda x: (x["kind"], x["id"]))
    return {"items": items[:limit], "total_items": len(items),
            "truncated": len(items) > limit, "read_only": True,
            "deleted": 0, "remote_deployments_verified": 0,
            "note": "Manifest/index inventories, not verified external publications."}
