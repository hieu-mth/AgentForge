"""Restrict static HTTP serving to trusted React build assets."""
import re
from agentforge.paths import UI_DASHBOARD_DIR

# React build output is a separate artifact, never a writable workspace file.
REACT_DIST = UI_DASHBOARD_DIR / "dist"
REACT_ASSET_RE = re.compile(r"[A-Za-z0-9_.-]{1,120}\.(?:js|css|svg|png|webp|ico)\Z")


def _react_asset(route):
    """Serve only allowlisted built files, no source files or path traversal."""
    if route in ("/dashboard", "/dashboard/"):
        file = REACT_DIST / "index.html"
        mime = "text/html; charset=utf-8"
    elif route.startswith("/dashboard/assets/"):
        name = route.removeprefix("/dashboard/assets/")
        if not REACT_ASSET_RE.fullmatch(name):
            raise ValueError("Invalid dashboard build asset")
        file = REACT_DIST / "assets" / name
        mime = {
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".webp": "image/webp",
            ".ico": "image/x-icon",
        }[file.suffix]
    else:
        raise ValueError("Not a React dashboard asset")
    if (not file.is_file() or file.is_symlink() or
            REACT_DIST.is_symlink() or file.parent.is_symlink()):
        raise FileNotFoundError("React build not installed; run npm run build")
    if file.stat().st_size > 7 * 1024 * 1024:
        raise ValueError("Dashboard build asset exceeds limit")
    return file.read_bytes(), mime
