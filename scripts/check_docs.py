"""Check relative Markdown links in tracked documentation scopes.

No network, subprocess, mutation, external dependencies or git requirement.
Use from repo root: python scripts/check_docs.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ("docs", "dashboard", "examples", "sandbox", "workers")
IGNORED = frozenset({".git", ".venv", "node_modules", "__pycache__", "dist",
                     "build", "workspace", "data", ".pytest_cache", ".vite"})
LINK = re.compile(r"!?\[[^\]\n]+\]\(([^)\n]+)\)")


def markdown_files(root: Path):
    """Walk only source-doc directories, not venv, dependencies or Owner data."""
    index = root / "README.md"
    if index.is_file():
        yield index
    for folder in SCOPES:
        base = root / folder
        if not base.is_dir():
            continue
        for current, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs
                       if d not in IGNORED and not (Path(current) / d).is_symlink()]
            for name in sorted(files):
                path = Path(current) / name
                if name.endswith(".md") and path.is_file() and not path.is_symlink():
                    yield path


def broken_links(root: Path):
    root = Path(root).resolve()
    broken = []
    for source in markdown_files(root):
        content = source.read_text(encoding="utf-8-sig")
        for match in LINK.finditer(content):
            href = match.group(1).strip().strip("<>")
            if not href or href.startswith("#"):
                continue
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                continue  # External URLs, mailto, data etc. are out of scope.
            target_name = unquote(parsed.path)
            if not target_name:
                continue
            target = (source.parent / target_name).resolve()
            if not target.is_relative_to(root) or not target.exists():
                broken.append((source.relative_to(root).as_posix(),
                               content.count("\n", 0, match.start()) + 1, href))
    return broken


def main():
    problems = broken_links(ROOT)
    if problems:
        for file, line, link in problems:
            print(f"{file}:{line}: unresolved relative link: {link}")
        print(f"Docs check FAILED: {len(problems)} broken link(s)")
        return 1
    print("Docs check PASS: all relative Markdown links in source scopes exist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
