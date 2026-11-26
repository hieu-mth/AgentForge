"""Owner-authenticated Model Hub configuration and explicit probes."""
import re
import threading
import sqlite3

from agentforge.ai import model_hub
from agentforge.api.routes._shared import UNHANDLED


_CHATGPT_ACTION = threading.Lock()


def _chatgpt_action(server, request, session):
    from agentforge.ai import chatgpt_auth
    from agentforge.ops_control import require_active
    if session is not None and set(request) == {"ack", "account_ref"} and request["ack"] == "CHATGPT_STATUS":
        ref = chatgpt_auth._ref(request["account_ref"])
        return {"account_ref": ref, "connected": chatgpt_auth.is_connected(ref)}
    if (session is None or not server.allow_external_actions
            or set(request) != {"ack", "account_ref"}
            or request["ack"] not in {"CONNECT_CHATGPT", "LIST_CHATGPT_MODELS", "DISCONNECT_CHATGPT"}):
        raise PermissionError("ChatGPT account actions require explicit Owner confirmation and external-tools mode.")
    ref = chatgpt_auth._ref(request["account_ref"])
    require_active()
    if not _CHATGPT_ACTION.acquire(blocking=False):
        raise ValueError("ChatGPT account action in progress.")
    try:
        if request["ack"] == "CONNECT_CHATGPT":
            chatgpt_auth.sign_in(ref)
            return {"account_ref": ref, "connected": True}
        if request["ack"] == "DISCONNECT_CHATGPT":
            result = chatgpt_auth.sign_out(ref)
            return {"account_ref": ref, "connected": False,
                    "remote_revocation": result["remote_revocation"]}
        models = []
        seen = set()
        for item in chatgpt_auth.models(ref):
            slug = item.get("slug")
            label = item.get("display_name")
            if (not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}", slug)
                    or slug in seen):
                continue
            seen.add(slug)
            models.append({"slug": slug, "display_name": label[:160] if isinstance(label, str) else slug})
            if len(models) == 200:
                break
        return {"account_ref": ref, "connected": True, "models": models}
    except chatgpt_auth.AuthError:
        raise
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error):
        raise ValueError("CHATGPT_ACCOUNT_ACTION_FAILED; check local connection or credentials.") from None
    finally:
        _CHATGPT_ACTION.release()


def handle(server, path, request, session=None):
    if path == "/api/model-hub/chatgpt":
        return _chatgpt_action(server, request, session)
    if path == "/api/model-hub/orchestrator":
        action = request.get("ack")
        if action == "SAVE_ORCHESTRATOR" and set(request) - {"route_changes"} == {
                "ack", "expected_revision", "policy"}:
            return model_hub.change(
                action, expected_revision=request["expected_revision"],
                policy=request["policy"], route_changes=request.get("route_changes"))
        if action == "RESET_ORCHESTRATOR" and set(request) == {"ack", "expected_revision"}:
            return model_hub.change(action, expected_revision=request["expected_revision"])
        raise PermissionError("Cần xác nhận lưu hoặc đặt lại chính sách điều phối")
    if path == "/api/model-hub/profile/preview":
        if (set(request) != {"ack", "expected_revision", "profile"}
                or request["ack"] != "PREVIEW_MODEL_PROFILE"):
            raise PermissionError("Explicit model profile preview required")
        return model_hub.preview_profile(request["profile"], expected_revision=request["expected_revision"])
    if path == "/api/model-hub/profile":
        if (set(request) - {"api_key", "intent"} != {"ack", "expected_revision", "profile"} or
                request["ack"] != "SAVE_MODEL_PROFILE"):
            raise PermissionError("Explicit model profile confirmation required")
        return model_hub.change(
            "SAVE_MODEL_PROFILE",
            expected_revision=request["expected_revision"],
            profile=request["profile"], api_key=request.get("api_key"), intent=request.get("intent"))
    if path == "/api/model-hub/profile/delete":
        if (set(request) != {"ack", "expected_revision", "profile_id"} or
                request["ack"] != "DELETE_MODEL_PROFILE"):
            raise PermissionError("Explicit model removal confirmation required")
        return model_hub.change(
            "DELETE_MODEL_PROFILE",
            expected_revision=request["expected_revision"],
            profile_id=request["profile_id"])
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
    if path == "/api/model-hub/readiness":
        if (set(request) != {"ack", "profile_id", "capability", "expected_revision"}
                or request["ack"] != "CHECK_CAPABILITY_READINESS"):
            raise PermissionError("Explicit read-only capability preflight required")
        return model_hub.capability_readiness(request["profile_id"], request["capability"],
                                              expected_revision=request["expected_revision"])
    if path == "/api/model-hub/check":
        if (set(request) != {"ack", "profile_id"} or
                request["ack"] != "CHECK_LOCAL_MODEL"):
            raise PermissionError("Explicit read-only local preflight required")
        return model_hub.check_local_profile(request["profile_id"])
    if path == "/api/model-hub/probe":
        if request.get("ack") in {"RUN_MEDIA_MODEL_PROBE", "POLL_MEDIA_MODEL_PROBE"}:
            if not server.allow_external_actions or session is None:
                raise PermissionError("Explicit Owner cloud media approval required")
            from agentforge.features.film_studio import media_probe
            return media_probe.handle(request)
        if request.get("ack") == "RUN_CLOUD_MODEL_PROBE":
            if set(request) != {"ack", "profile_id", "expected_revision"} or not server.allow_external_actions:
                raise PermissionError("Explicit cloud inference approval required")
            from agentforge.ops_control import require_active
            require_active()
            return model_hub.probe_cloud_profile(request["profile_id"],
                                                 expected_revision=request["expected_revision"])
        if request.get("ack") == "RUN_FLUX_MODEL_PROBE":
            fields = {"ack", "profile_id", "expected_revision", "prompt"}
            options = {"width", "height", "steps", "seed"}
            if (set(request) - options != fields or not server.allow_external_actions
                    or not isinstance(request.get("profile_id"), str)):
                raise PermissionError("Explicit local inference approval and external-tools mode required")
            from agentforge.features.media.flux_runtime import generate
            with model_hub.local_inference_slot():
                return generate(request["prompt"], profile_id=request["profile_id"],
                                expected_revision=request["expected_revision"],
                                **{key: request[key] for key in options & request.keys()})
        if (set(request) != {"ack", "profile_id", "expected_revision"} or
                request["ack"] != "RUN_LOCAL_MODEL_PROBE" or not server.allow_external_actions):
            raise PermissionError("Explicit local inference approval and external-tools mode required")
        from agentforge.ops_control import require_active
        require_active()
        with model_hub.local_inference_slot():
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
