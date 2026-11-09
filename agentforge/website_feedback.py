"""Compatibility shim. Canonical feedback: agentforge.features.websites.feedback."""
from agentforge.features.websites.feedback import (
    MAX_FEEDBACK, MIN_FEEDBACK, request_revision,
)

__all__ = ["request_revision", "MAX_FEEDBACK", "MIN_FEEDBACK"]
