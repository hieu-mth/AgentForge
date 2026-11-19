"""Owner-authenticated Model Hub configuration and explicit probes."""
from agentforge.ai import model_hub
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path == "/api/model-hub/orchestrator":
        action = request.get("ack")
        if action == "SAVE_ORCHESTRATOR" and set(request) == {
                "ack", "expected_revision", "policy", "route_changes"}:
            return model_hub.change(
                action, expected_revision=request["expected_revision"],
                policy=request["policy"], route_changes=request["route_changes"])
        if action == "RESET_ORCHESTRATOR" and set(request) == {"ack", "expected_revision"}:
            return model_hub.change(action, expected_revision=request["expected_revision"])
        raise PermissionError("Cần xác nhận lưu hoặc đặt lại chính sách điều phối")
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
    if path == "/api/model-hub/check":
        if (set(request) != {"ack", "profile_id"} or
                request["ack"] != "CHECK_LOCAL_MODEL"):
            raise PermissionError("Explicit read-only local preflight required")
        return model_hub.check_local_profile(request["profile_id"])
    if path == "/api/model-hub/probe":
        if (set(request) != {"ack", "profile_id", "expected_revision"} or
                request["ack"] != "RUN_LOCAL_MODEL_PROBE" or not server.allow_external_actions):
            raise PermissionError("Explicit local inference approval and external-tools mode required")
        from agentforge.ops_control import require_active
        require_active()
        return model_hub.probe_local_profile(
            request["profile_id"], expected_revision=request["expected_revision"])
    if path == "/api/model-hub/rollback":
        if (set(request) != {"ack", "expected_revision", "target_revision"} or
                request["ack"] != "ROLLBACK_MODEL_HUB"):
            raise PermissionError("Explicit model config rollback required")
        return model_hub.change(
            "ROLLBACK_MODEL_HUB",
            expected_revision=request["expected_revision"],
            target_revision=request["target_revision"])
    return UNHANDLED
