"""Owner pause/resume control; no implicit process execution."""
from agentforge import ops_control
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path == "/api/ops/comfyui/config":
        if set(request) != {"profile_id", "install_root"}:
            raise ValueError("Expected ComfyUI profile ID and Portable folder")
        from agentforge.integrations import comfy_service
        return comfy_service.configure(request["profile_id"], request["install_root"])
    if path == "/api/ops/comfyui/control":
        action = request.get("action")
        if (not server.allow_external_actions or set(request) != {"action"}
                or not isinstance(action, str) or action not in {"start", "stop", "restart"}):
            raise PermissionError("ComfyUI controls require external-tools mode and a supported action")
        from agentforge.ai.model_hub import local_inference_slot
        from agentforge.integrations import comfy_service
        with local_inference_slot():
            return comfy_service.control(action)
    if path == "/api/ops/control":
        mode = request.get("mode")
        expected = "PAUSE_OPERATIONS" if mode == "PAUSED" else (
            "RESUME_OPERATIONS" if mode == "ACTIVE" else None)
        if expected is None or request.get("ack") != expected:
            raise PermissionError("Explicit matching operations control acknowledgment required")
        return ops_control.set_mode(mode, confirm=True)
    return UNHANDLED
