"""Compatibility shim. Canonical preview: agentforge.domains.websites.preview."""
from agentforge.domains.websites.preview import (
    MAX_PREVIEW_BYTES, STYLESHEET, HEAD_END, STYLE_END, from_proposal,
)

__all__ = ["from_proposal", "MAX_PREVIEW_BYTES"]
