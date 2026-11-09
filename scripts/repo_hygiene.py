"""Safe local repository hygiene. Default is inventory only; no touching user data.

Scope: disposable Python cache files in agentforge/ and tests/ only. Runtime data,
workspace artifacts, model weights, .env, SQLite and proposal history are NEVER
pruned by this tool. No recursive traversal through junctions or symlinks.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = (ROOT / "agentforge", ROOT / "tests")


def _link(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def inventory():
    found = []
    for base in SCOPES:
        if not base.exists() or _link(base):
            continue
        # Walk only directory names that have been individually validated.
        stack = [base]
        while stack:
            folder = stack.pop()
            if _link(folder):
                continue
            for path in folder.iterdir():
                if _link(path):
                    continue
                if path.is_dir():
                    if path.name == "__pycache__":
                        for file in path.iterdir():
                            if not _link(file) and file.is_file() and file.suffix == ".pyc":
                                found.append(file)
                    else:
                        stack.append(path)
    return sorted(found)


def report(*, clean=False, confirm=False):
    files = inventory()
    total = sum(p.stat().st_size for p in files)
    if clean and confirm is not True:
        raise PermissionError("Explicit --confirm-cache-clean required")
    deleted = 0
    if clean:
        for p in files:
            if _link(p) or _link(p.parent) or not p.is_file() or p.suffix != ".pyc":
                continue
            p.unlink()
            deleted += 1
    return {
        "mode": "CLEAN_CACHE" if clean else "READ_ONLY",
        "pyc_files": len(files), "bytes": total,
        "deleted": deleted, "scopes": ["agentforge/", "tests/"],
        "runtime_data_deleted": False, "user_artifacts_deleted": False,
    }


def main():
    parser = argparse.ArgumentParser(description="AgentForge safe, local cache inventory")
    parser.add_argument("action", choices=["report", "clean-cache"])
    parser.add_argument("--confirm-cache-clean", action="store_true")
    args = parser.parse_args()
    print(json.dumps(report(clean=args.action == "clean-cache",
                            confirm=args.confirm_cache_clean), indent=2))


if __name__ == "__main__":
    main()
