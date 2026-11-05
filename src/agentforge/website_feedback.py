"""Compatibility shim. Canonical feedback: agentforge.domains.websites.feedback."""
from agentforge.domains.websites.feedback import (
    MAX_FEEDBACK, MIN_FEEDBACK, request_revision,
)

__all__ = ["request_revision", "MAX_FEEDBACK", "MIN_FEEDBACK"]
