"""Owner pause/resume control; no implicit process execution."""
from agentforge import ops_control
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path == "/api/ops/control":
        mode = request.get("mode")
        expected = "PAUSE_OPERATIONS" if mode == "PAUSED" else (
            "RESUME_OPERATIONS" if mode == "ACTIVE" else None)
        if expected is None or request.get("ack") != expected:
            raise PermissionError("Explicit matching operations control acknowledgment required")
        return ops_control.set_mode(mode, confirm=True)
    return UNHANDLED
