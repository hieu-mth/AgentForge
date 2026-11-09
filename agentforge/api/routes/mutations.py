"""Stable Owner-action dispatcher; route branches are maintained by feature family.

Every module returns UNHANDLED if its route does not match; a matched action
may legitimately return None, so no truthiness-based fallback is permitted.
Policy/Owner approval remains in the matching trusted handler.
"""
from agentforge.api.routes import artifacts, media, workspace, operations, products, goals, model_hub
from agentforge.api.routes._shared import UNHANDLED


ROUTE_HANDLERS = (
    artifacts.handle, media.handle, workspace.handle,
    operations.handle, products.handle, goals.handle, model_hub.handle,
)


def _owner_action(server, path, request, session=None):
    """Process one explicitly allowed mutation, preserving error/return semantics."""
    for handler in ROUTE_HANDLERS:
        result = handler(server, path, request, session)
        if result is not UNHANDLED:
            return result
    raise ValueError("Unknown mutation route")
