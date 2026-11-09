"""Owner-authenticated Model Hub actions; model configuration never runs inference."""
from agentforge.ai import model_hub
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path == "/api/model-hub/profile":
        if (set(request) != {"ack", "expected_revision", "profile"} or
                request["ack"] != "SAVE_MODEL_PROFILE"):
            raise PermissionError("Explicit model profile confirmation required")
        return model_hub.change(
            "SAVE_MODEL_PROFILE",
            expected_revision=request["expected_revision"],
            profile=request["profile"])
    if path == "/api/model-hub/route":
        if (set(request) != {"ack", "expected_revision", "task_id", "model_ref"} or
                request["ack"] != "SET_MODEL_ROUTE"):
            raise PermissionError("Explicit model route confirmation required")
        return model_hub.change(
            "SET_MODEL_ROUTE",
            expected_revision=request["expected_revision"],
            task_id=request["task_id"], model_ref=request["model_ref"])
    if path == "/api/model-hub/reset":
        if (set(request) != {"ack", "expected_revision", "task_id"} or
                request["ack"] != "RESET_MODEL_ROUTE"):
            raise PermissionError("Explicit model route reset required")
        return model_hub.change(
            "RESET_MODEL_ROUTE",
            expected_revision=request["expected_revision"],
            task_id=request["task_id"])
    if path == "/api/model-hub/rollback":
        if (set(request) != {"ack", "expected_revision", "target_revision"} or
                request["ack"] != "ROLLBACK_MODEL_HUB"):
            raise PermissionError("Explicit model config rollback required")
        return model_hub.change(
            "ROLLBACK_MODEL_HUB",
            expected_revision=request["expected_revision"],
            target_revision=request["target_revision"])
    return UNHANDLED
