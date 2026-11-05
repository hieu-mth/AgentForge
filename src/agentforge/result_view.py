"""Compatibility shim. Canonical projection: agentforge.core.result_view."""
from agentforge.core.result_view import (
    ANALYTICS, GROWTH, SCALARS, NUMERIC, SIGNALS, WARNINGS,
    _scalar, _picked, present,
)

__all__ = ["present", "ANALYTICS", "GROWTH", "SCALARS", "NUMERIC", "SIGNALS", "WARNINGS"]
