"""Architecture contract for Video Studio runtime boundaries and local data ownership.

This is an audit-friendly reference, not a dynamic module loader. It must not
walk or delete user data or alter import paths at runtime.
"""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent

LAYOUT = {
    "api": "agentforge/control_center_v1.py",
    "ai": "agentforge/ai",
    "core": "agentforge/core",
    "ops": "agentforge/ops",
    "media_feature": "agentforge/features/media",
    "film_studio_feature": "agentforge/features/film_studio",
    "comfyui_integration": "agentforge/integrations/comfyui.py",
    "storage": "agentforge/storage",
    "ui": "dashboard",
    "contracts": "skills",
    "runtime_data": "data",
    "generated_products": "workspace",
    "tests": "tests",
    "ops_scripts": "scripts",
}
PERSISTENT_DIRS = frozenset(("data", "workspace"))
GENERATED_DIRS = frozenset(("dashboard/dist", "dashboard/node_modules"))
LEGACY_IMPORTS = {
    "agentforge.prompt_intake": "agentforge.ai.prompt_intake",
    "agentforge.result_view": "agentforge.core.result_view",
    "agentforge.artifact_catalog": "agentforge.storage.artifact_catalog",
    "agentforge.model_health": "agentforge.ai.model_health",
}


def snapshot():
    """Read-only structure facts, never a recursive runtime file scan."""
    return {
        "repository_root": str(REPOSITORY_ROOT),
        "layout": dict(LAYOUT),
        "persistent": sorted(PERSISTENT_DIRS),
        "generated": sorted(GENERATED_DIRS),
        "compatibility_imports": dict(LEGACY_IMPORTS),
        "data_cleanup_allowed": False,
        "workspace_cleanup_allowed": False,
    }
