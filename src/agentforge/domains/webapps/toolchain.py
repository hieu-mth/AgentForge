"""Reviewed, locked scaffold data. No generated code is imported or executed."""
import json
from agentforge.paths import REPOSITORY_ROOT

REFERENCE = REPOSITORY_ROOT / "examples" / "novamart"


def project_files(slug, *, legacy=False):
    package = json.loads((REFERENCE / "package.json").read_text(encoding="utf-8"))
    package["name"] = "@agentforge/" + slug
    package["scripts"].pop("test:browser", None)
    package["devDependencies"].pop("playwright-core", None)
    if legacy:
        # Exact pre-Phase-1 scaffold, for immutable historical proposal reads.
        # Never rewrite old files/SHA or silently treat old dependencies as patched.
        package["devDependencies"]["vite"] = "7.3.1"
        package.pop("overrides", None)
        return {"package.json": json.dumps(package, indent=2) + "\n"}
    lock = json.loads((REFERENCE / "package-lock.json").read_text(encoding="utf-8"))
    lock["name"] = package["name"]
    lock["packages"][""]["name"] = package["name"]
    lock["packages"][""]["devDependencies"] = package["devDependencies"]
    # Unreachable reference-only browser tooling is not part of generated apps.
    lock["packages"].pop("node_modules/playwright-core", None)
    return {"package.json": json.dumps(package, indent=2) + "\n",
            "package-lock.json": json.dumps(lock, separators=(",", ":")) + "\n"}


def require_current(files):
    """Old proposals remain readable, but cannot use the current QA image."""
    entries = {item["path"]: item["content"] for item in files}
    package = json.loads(entries["package.json"])
    slug = package["name"].removeprefix("@agentforge/")
    expected = project_files(slug)
    if any(entries.get(name) != content for name, content in expected.items()):
        raise ValueError("TOOLCHAIN_STALE: create a new proposal with the patched locked scaffold")
