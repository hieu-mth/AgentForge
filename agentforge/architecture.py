"""Architecture contract for stable domain imports and runtime data ownership.

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
    "website_domain": "agentforge/features/websites",
    "growth_feature": "agentforge/features/growth",
    "webapp_feature": "agentforge/features/webapps",
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
    "agentforge.website_preview": "agentforge.features.websites.preview",
    "agentforge.website_feedback": "agentforge.features.websites.feedback",
    "agentforge.artifact_catalog": "agentforge.storage.artifact_catalog",
    "agentforge.model_health": "agentforge.ai.model_health",
}


BUSINESS_DOMAIN_IMPORTS = {
    "agentforge.product_builder": "agentforge.features.websites.builder",
    "agentforge.web_assets": "agentforge.features.websites.assets",
    "agentforge.product_quality": "agentforge.features.websites.quality",
    "agentforge.product_revision": "agentforge.features.websites.revision",
    "agentforge.web_design_kit": "agentforge.features.websites.design_kit",
    "agentforge.browser_validation": "agentforge.features.websites.browser_validation",
    "agentforge.image_studio_v24": "agentforge.features.websites.image_studio",
    "agentforge.media_assets": "agentforge.features.media.assets",
    "agentforge.media_quality": "agentforge.features.media.quality",
    "agentforge.media_render": "agentforge.features.media.render",
    "agentforge.media_workflow_v15": "agentforge.features.media.workflow",
    "agentforge.growth_store": "agentforge.features.growth.store",
    "agentforge.growth_reports": "agentforge.features.growth.reports",
    "agentforge.growth_bundle": "agentforge.features.growth.bundle",
}


def snapshot():
    """Read-only structure facts, never a recursive runtime file scan."""
    return {
        "repository_root": str(REPOSITORY_ROOT),
        "layout": dict(LAYOUT),
        "persistent": sorted(PERSISTENT_DIRS),
        "generated": sorted(GENERATED_DIRS),
        "compatibility_imports": dict(LEGACY_IMPORTS),
        "business_domain_imports": dict(BUSINESS_DOMAIN_IMPORTS),
        "data_cleanup_allowed": False,
        "workspace_cleanup_allowed": False,
    }
