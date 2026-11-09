"""M5 read-only inventory of retained public root compatibility imports.

No aliases are deleted: static repository callers are not proof that external
scripts or installed editable packages do not depend on historical names.
Reads only trusted repository Python sources; never data/ or workspace/.
"""
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "websites": {
        "product_builder": "builder", "product_quality": "quality",
        "product_revision": "revision", "web_assets": "assets",
        "web_design_kit": "design_kit", "browser_validation": "browser_validation",
        "image_studio_v24": "image_studio", "website_preview": "preview",
        "website_feedback": "feedback",
    },
    "webapps": {
        "webapp_builder": "builder", "webapp_developer": "developer",
        "webapp_sandbox": "sandbox", "webapp_architect": "architect",
        "webapp_reviewer": "reviewer", "webapp_static_qa": "static_qa",
    },
    "media": {
        "media_assets": "assets", "media_render": "render",
        "media_quality": "quality", "media_workflow_v15": "workflow",
    },
    "growth": {
        "growth_store": "store", "growth_bundle": "bundle",
        "growth_reports": "reports",
    },
}
TARGETS = {
    name: f"agentforge.features.{group}.{module}"
    for group, names in GROUPS.items() for name, module in names.items()
}
SCOPES = ("agentforge", "tests", "scripts")
MAX_SOURCE_BYTES = 512_000


def _safe_regular(path):
    for p in (path, *path.parents):
        if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
            return False
    return path.is_file() and path.stat().st_size <= MAX_SOURCE_BYTES


def _source(root, path):
    absolute = root / path
    if not _safe_regular(absolute):
        return None
    return absolute.read_text(encoding="utf-8-sig")


def _references(tree, name):
    full = "agentforge." + name
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            n.name == full or n.name.startswith(full + ".") for n in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (
            node.module == full or (node.module or "").startswith(full + ".")
            or (node.module == "agentforge" and any(n.name == name for n in node.names))
        ):
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and (
            node.value == full or node.value.startswith(full + ".")
        ):
            return True
    return False


def report(*, root=None, targets=None):
    root = Path(root) if root is not None else ROOT
    targets = TARGETS if targets is None else targets
    seen = {}
    for scope in SCOPES:
        base = root / scope
        if not base.is_dir() or base.is_symlink():
            continue
        for path in base.rglob("*.py"):
            if not _safe_regular(path):
                continue
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8-sig")
                seen[relative] = ast.parse(source, filename=relative)
            except (OSError, UnicodeError, SyntaxError):
                # Incomplete static coverage must never grant permission to delete.
                seen[relative] = None
    rows = []
    for name, target in sorted(targets.items()):
        path = "agentforge/" + name + ".py"
        source = _source(root, path)
        base, member = target.rsplit(".", 1)
        source_ok = bool(source and "agentforge.domains." not in source
                         and (f"from {base} import {member}" in source
                              or f"from {target} import " in source))
        callers = sorted(
            relative for relative, tree in seen.items()
            if tree is not None and relative != path and _references(tree, name)
        )
        rows.append({
            "alias": "agentforge." + name,
            "canonical": target,
            "source_ok": source_ok,
            "internal_references": callers,
            "external_callers_unverified": True,
            "safe_to_delete": False,
        })
    return {
        "status": "PASS" if all(row["source_ok"] for row in rows) and rows else "FAIL",
        "aliases_checked": len(rows),
        "aliases": rows,
        "scope": list(SCOPES),
        "static_scan_only": True,
        "external_callers_unverified": True,
        "aliases_removed": 0,
        "owner_data_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only compatibility import audit")
    parser.add_argument("--check", action="store_true",
                        help="Fail if an expected root alias no longer targets a canonical feature")
    args = parser.parse_args()
    result = report()
    print(json.dumps(result, indent=2, ensure_ascii=True))
    if args.check and result["status"] != "PASS":
        parser.exit(2)


if __name__ == "__main__":
    main()
