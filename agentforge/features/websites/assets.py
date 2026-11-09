"""Local raster images for static-web products (Web Design V2).

No remote downloads or image generation. Images are user-supplied, immutable,
bounded, and stored under the existing gitignored product directory.
SVG is deliberately not accepted here because it may contain active content.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from agentforge import product_builder as builder

NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}\.(?:png|jpg|jpeg|webp)\Z")
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_IMAGES = 12
MAX_ALL_BYTES = 30 * 1024 * 1024
MIMES = {"png": "image/png", "jpg": "image/jpeg",
         "jpeg": "image/jpeg", "webp": "image/webp"}


def valid_name(name):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError("Asset must be a flat lowercase .png/.jpg/.jpeg/.webp filename")
    return name


def _project(slug):
    slug = builder._check_slug(slug)
    root = builder.PRODUCTS / slug
    builder._check_path_chain(root)
    if not (root / "index.html").is_file():
        raise FileNotFoundError("Existing project index.html required")
    return root


def _path(slug, name):
    root = _project(slug)
    path = root / "assets" / valid_name(name)
    builder._check_path_chain(path)
    return path


def _format(data, suffix):
    if suffix == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR"
    if suffix in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    if suffix == "webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return False


def _read_image(path, name):
    builder._check_path_chain(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError("Image missing, empty or exceeds 6 MiB")
    contents = path.read_bytes()
    if not 0 < len(contents) <= MAX_IMAGE_BYTES or not _format(contents, name.rsplit(".", 1)[1]):
        raise ValueError("Not a supported raster image; SVG and active formats forbidden")
    return contents


def list_images(slug):
    root = _project(slug)
    folder = root / "assets"
    builder._check_path_chain(folder)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ValueError("Assets directory is not a directory")
    result = []
    total = 0
    for path in sorted(folder.iterdir()):
        builder._check_path_chain(path)
        valid_name(path.name)
        contents = _read_image(path, path.name)
        total += len(contents)
        if total > MAX_ALL_BYTES or len(result) >= MAX_IMAGES:
            raise ValueError("Asset limits exceeded")
        result.append({"name": path.name, "bytes": len(contents),
                       "sha256": hashlib.sha256(contents).hexdigest()})
    return result


def read_image(slug, name):
    contents = _read_image(_path(slug, name), name)
    return contents, MIMES[name.rsplit(".", 1)[1]]


def references(html):
    """Only supported asset images: <img src='assets/flat-name.ext'>.

    Other URLs are handled by existing C8 static/security checks. This
    function never interprets CSS, scripts or arbitrary remote references.
    """
    from html.parser import HTMLParser

    class Images(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.refs = []
        def handle_starttag(self, tag, attrs):
            if tag != "img":
                return
            src = dict(attrs).get("src", "")
            if src.startswith("assets/"):
                self.refs.append(valid_name(src.removeprefix("assets/")))
        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

    parser = Images()
    parser.feed(html)
    parser.close()
    return sorted(set(parser.refs))


def verify_references(slug, html):
    assets = []
    for name in references(html):
        contents, _ = read_image(slug, name)
        assets.append({"name": name, "bytes": len(contents),
                       "sha256": hashlib.sha256(contents).hexdigest()})
    return assets


def import_image(slug, source_path, name, *, confirm_write=False):
    """Copy one owner-supplied raster; no overwrite and no remote download."""
    if confirm_write is not True:
        raise PermissionError("Explicit --confirm-write required for image import")
    target = _path(slug, name)
    source = Path(source_path).expanduser()
    # Check the entire source chain BEFORE following paths. Never resolve away
    # symlinks/junctions. Files in the user's photo library are untrusted.
    builder._check_path_chain(source)
    contents = _read_image(source, name)
    assets = list_images(slug)
    if len(assets) >= MAX_IMAGES or sum(x["bytes"] for x in assets) + len(contents) > MAX_ALL_BYTES:
        raise ValueError("Product image asset budget exceeded")
    target.parent.mkdir(parents=True, exist_ok=True)
    builder._check_path_chain(target)
    with target.open("xb") as dest:
        dest.write(contents)
    if target.read_bytes() != contents:
        raise IOError("Imported image verification failed")
    return {"status": "LOCAL_IMAGE_IMPORTED", "project_slug": slug,
            "asset": "assets/" + name, "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "deployment_authorized": False}


def main():
    parser = argparse.ArgumentParser(description="Owner-approved local raster asset import")
    subs = parser.add_subparsers(dest="action", required=True)
    p = subs.add_parser("list")
    p.add_argument("slug")
    p = subs.add_parser("import")
    p.add_argument("slug")
    p.add_argument("source_path", help="Path to a real photo on this computer")
    p.add_argument("name", help="Safe destination name, e.g. hero.jpg")
    p.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    result = (list_images(args.slug) if args.action == "list" else
              import_image(args.slug, args.source_path, args.name,
                           confirm_write=args.confirm_write))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
