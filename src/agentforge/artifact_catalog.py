"""Compatibility shim. Canonical inventory: agentforge.storage.artifact_catalog."""
from agentforge.storage.artifact_catalog import LIMIT, _safe, _children, report

__all__ = ["report", "LIMIT"]
