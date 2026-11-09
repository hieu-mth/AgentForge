"""Canonical local project paths. Never infer root from a moved domain module.

This module is the only owner of the source-tree root calculation. Runtime
databases and user products must remain where existing AgentForge releases
stored them. No directories are created at import time.
"""
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPOSITORY_ROOT / "config"
WORKERS_DIR = REPOSITORY_ROOT / "workers"
DATA_DIR = REPOSITORY_ROOT / "data"
COMPANY_DATA_DIR = DATA_DIR / "company"
WORKSPACE_DIR = REPOSITORY_ROOT / "workspace"
PRODUCTS_DIR = WORKSPACE_DIR / "products"
MEDIA_DIR = WORKSPACE_DIR / "media"
UI_DASHBOARD_DIR = REPOSITORY_ROOT / "dashboard"

def ensure_local_root(path: Path) -> Path:
    """Reject paths traversing a Windows junction/symlink before local writes."""
    target = Path(path)
    for ancestor in (target, *target.parents):
        if ancestor.is_symlink() or (
            hasattr(ancestor, "is_junction") and ancestor.is_junction()
        ):
            raise PermissionError("Linked storage path refused")
    return target
