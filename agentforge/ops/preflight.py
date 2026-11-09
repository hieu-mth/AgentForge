"""M9: bounded, read-only environment inspection for local Owner setup.

No subprocess, network call, provider probing, import of optional model
libraries, state creation, dependency installation or inspection of secrets.
The returned object has only fixed labels, statuses and safe relative hints.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from agentforge.paths import REPOSITORY_ROOT

MINIMUM_PYTHON = (3, 13)
CHECKS = (
    ("source", "Python package", "agentforge/__main__.py", "file"),
    ("pyproject", "Python packaging", "pyproject.toml", "file"),
    ("dashboard_source", "Dashboard source", "dashboard/package.json", "file"),
    ("dashboard_build", "Dashboard build", "dashboard/dist/index.html", "file"),
    ("model_defaults", "Model registry", "config/models.toml", "file"),
    ("task_routes", "Task routing", "config/task_routes.toml", "file"),
    ("worker_manifests", "Workers", "workers", "dir"),
)
REQUIRED = frozenset({"source", "pyproject", "dashboard_source", "model_defaults",
                      "task_routes", "worker_manifests"})


def _path_status(root, relative, kind):
    """Refuse symlink/junction substitution without reading file contents."""
    root = Path(root)
    target = root / relative
    try:
        for item in (root, *target.parents, target):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                return "BLOCKED"
        if not target.exists():
            return "NEEDS_SETUP"
        if (target.is_file() if kind == "file" else target.is_dir()):
            if kind == "file" and target.stat().st_size == 0:
                return "BLOCKED"
            return "READY"
    except (OSError, ValueError):
        return "BLOCKED"
    return "BLOCKED"


def inspect(*, root=None, version=None, which=None):
    """Inspect only known trusted files and executable presence, never run them."""
    project = Path(root) if root is not None else REPOSITORY_ROOT
    version = tuple(version) if version is not None else tuple(sys.version_info[:3])
    locate = which if which is not None else shutil.which
    results = []
    py_ready = version[:2] >= MINIMUM_PYTHON
    results.append({
        "id": "python", "label": "Python runtime",
        "status": "READY" if py_ready else "BLOCKED",
        "detail": "Python " + ".".join(map(str, version[:3])) +
                  (" (3.13+)" if py_ready else " (yêu cầu >= 3.13)"),
    })
    for ident, label, rel, kind in CHECKS:
        state = _path_status(project, rel, kind)
        results.append({
            "id": ident, "label": label, "status": state,
            "detail": rel + (" · Cần build bằng npm" if ident == "dashboard_build"
                            and state == "NEEDS_SETUP" else ""),
        })
    for ident, label, binary in (
        ("node", "Node.js", "node"),
        ("npm", "npm", "npm.cmd" if os.name == "nt" else "npm"),
    ):
        present = locate(binary) is not None
        results.append({
            "id": ident, "label": label,
            "status": "AVAILABLE_UNVERIFIED" if present else "NEEDS_SETUP",
            "detail": "Đã tìm thấy · phiên bản chưa kiểm tra" if present else
                      "Chưa tìm thấy trong PATH",
        })
    critical = any(item["status"] == "BLOCKED" or
                   (item["id"] in REQUIRED and item["status"] != "READY")
                   for item in results)
    needs = any(item["status"] == "NEEDS_SETUP" for item in results)
    return {
        "status": "BLOCKED" if critical else
                  "REVIEW_REQUIRED" if needs else "READY_LOCAL_UNVERIFIED",
        "checks": results,
        "read_only": True,
        "network_called": False,
        "installation_performed": False,
        "provider_models_tested": False,
        "generated_source_executed": False,
    }


def main():
    parser = argparse.ArgumentParser(description="AgentForge read-only Windows setup preflight")
    parser.add_argument("--strict", action="store_true",
                        help="Nonzero exit if any requirement or optional check is missing")
    args = parser.parse_args()
    result = inspect()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "BLOCKED" or (
            args.strict and result["status"] != "READY_LOCAL_UNVERIFIED"):
        parser.exit(2)


if __name__ == "__main__":
    main()
