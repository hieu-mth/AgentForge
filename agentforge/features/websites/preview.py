"""Read-only, isolated visual previews of immutable product proposals.

The browser receives only a digest-verified proposed HTML document. It is
framed by an authenticated owner page with a sandboxed iframe and a dedicated
no-script, no-network CSP. Never writes files or executes a website.
"""
import re

from agentforge import product_builder

MAX_PREVIEW_BYTES = 32000
STYLESHEET = re.compile(
    r"""<link\b(?=[^>]*\brel\s*=\s*["']stylesheet["'])(?=[^>]*\bhref\s*=\s*["']styles\.css["'])[^>]*>""",
    re.IGNORECASE,
)
HEAD_END = re.compile(r"</head\s*>", re.IGNORECASE)
STYLE_END = re.compile(r"</style", re.IGNORECASE)


def from_proposal(proposal_id):
    doc, _ = product_builder._read_proposal(proposal_id)
    if doc["status"] != "PROPOSED_NOT_APPLIED":
        raise PermissionError("Only pending owner proposals have a preview")
    files = {item["path"]: item["content"] for item in doc["files"]}
    html = files["index.html"]
    # Defence-in-depth: reuse the exact product gate, don't trust persisted flags.
    product_builder._require_static_quality(html)
    if "styles.css" in files:
        css = files["styles.css"]
        if STYLE_END.search(css):
            raise ValueError("CSS may not close the preview style element")
        insertion = "<style>\n" + css + "\n</style>"
        html = STYLESHEET.sub("", html)
        if not HEAD_END.search(html):
            raise ValueError("Missing head end")
        html = HEAD_END.sub(lambda _: insertion + "</head>", html, count=1)
    raw = html.encode("utf-8")
    if not 0 < len(raw) <= MAX_PREVIEW_BYTES:
        raise ValueError("Preview HTML exceeds bounded size")
    return raw
