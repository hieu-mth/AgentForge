"""Explicit Owner actions for video, models and local operations."""
from agentforge.api.routes import media, operations, model_hub, publishing, characters
from agentforge.api.routes._shared import UNHANDLED

ROUTE_HANDLERS = (
    media.handle, operations.handle, model_hub.handle,
    publishing.handle, characters.handle,
)


def _owner_action(server, path, request, session=None):
    for handler in ROUTE_HANDLERS:
        result = handler(server, path, request, session)
        if result is not UNHANDLED:
            return result
    raise ValueError("Unknown mutation route")
