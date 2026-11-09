"""Workspace intake and bounded model delegation policy."""
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path == "/api/workspace/policy":
        from agentforge import workspace_policy
        if (set(request) != {"ack", "max_estimated_model_calls",
                             "website_enabled", "storyboard_enabled"} or
                request.get("ack") != "UPDATE_WORKSPACE_POLICY"):
            raise PermissionError("Only explicit bounded owner workspace policy is allowed")
        return workspace_policy.configure(
            max_estimated_model_calls=request["max_estimated_model_calls"],
            website_enabled=request["website_enabled"],
            storyboard_enabled=request["storyboard_enabled"], confirm=True)
    if path == "/api/workspace/request":
        if set(request) != {"ack", "prompt", "max_model_calls"} or request.get("ack") != "PLAN_ONLY":
            raise PermissionError("Chỉ được tạo kế hoạch sau xác nhận owner.")
        from agentforge.prompt_intake import plan_request
        return plan_request(
            request["prompt"], max_model_calls=request["max_model_calls"],
            max_external_runs=0, brain_db_path=server.brain_db_path,
            analytics_db_path=server.analytics_db_path,
            growth_db_path=server.growth_db_path)
    if path == "/api/autopilot/configure":
        from agentforge import autopilot_v13
        if request.get("ack") != "SET_DAILY_MODEL_POLICY":
            raise PermissionError("Owner must explicitly approve standing delegation")
        if set(request) != {"ack", "enabled", "daily_cap"}:
            raise ValueError("Only bounded policy fields accepted")
        return autopilot_v13.configure(
            enabled=request["enabled"], daily_cap=request["daily_cap"],
            confirm=True)
    return UNHANDLED
