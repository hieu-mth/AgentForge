"""Local media/image review and explicit generation approvals."""
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path == "/api/image/submit":
        from agentforge.image_studio_v24 import submit
        if not server.allow_external_actions:
            raise PermissionError("ComfyUI image generation requires external-capable owner mode")
        if set(request) != {"ack", "slug", "prompt", "checkpoint"} or request.get("ack") != "GENERATE_LOCAL_IMAGE":
            raise PermissionError("Explicit owner image generation request required")
        return submit(request["slug"], request["prompt"], request["checkpoint"],
                      confirm_generation=True)
    if path.startswith("/api/image/") and path.endswith("/collect"):
        from agentforge.image_studio_v24 import collect
        if not server.allow_external_actions:
            raise PermissionError("Image import requires external-capable owner mode")
        parts = path.split("/")
        if len(parts) != 5 or set(request) != {"ack"} or request["ack"] != "IMPORT_AI_IMAGE":
            raise PermissionError("Explicit owner image import required")
        return collect(parts[3], confirm_import=True)
    if path.startswith("/api/image/") and path.endswith("/attach"):
        from agentforge.image_studio_v24 import attach
        if set(request) != {"ack", "image_sha", "html_sha"} or request["ack"] != "ATTACH_AI_IMAGE":
            raise PermissionError("Explicit SHA-bound owner image attachment required")
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid image job route")
        return attach(parts[3], request["image_sha"], request["html_sha"],
                      confirm_attach=True)
    if path.startswith("/api/videos/") and path.endswith("/decide"):
        from agentforge import media_workflow_v15
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid video review route")
        ident = parts[3]
        if set(request) != {"ack", "decision", "video_sha", "watched_local_file"}:
            raise ValueError("Only bounded video approval fields accepted")
        decision = request["decision"]
        if decision not in ("APPROVE", "REJECT") or request["ack"] != "VIDEO_" + decision:
            raise PermissionError("Explicit video decision required")
        if request["watched_local_file"] is not True:
            raise PermissionError("Owner must confirm watching local MP4")
        if (session is None or
                session.get("inspected_video", {}).get(ident) != request["video_sha"]):
            raise PermissionError("Inspect exact MP4 metadata in this session first")
        return media_workflow_v15.decide(
            ident, decision, request["video_sha"], confirm_review=True)
    if path.startswith("/api/drafts/") and path.endswith("/decide"):
        from agentforge import quality_v14
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid content review route")
        job_id = parts[3]
        if set(request) != {"ack", "decision", "output_sha"}:
            raise ValueError("Only bounded content review fields accepted")
        decision = request["decision"]
        if decision not in ("APPROVE", "REJECT") or request["ack"] != "REVIEW_" + decision:
            raise PermissionError("Explicit exact owner decision required")
        if (decision == "APPROVE" and
                (session is None or session.get("reviewed_ai_drafts", {}).get(job_id)
                 != request["output_sha"])):
            raise PermissionError("Inspect the full task in this session before approving")
        return quality_v14.decide(
            job_id, decision, request["output_sha"], confirm=True)
    if path == "/api/media/prepare":
        if request.get("ack") != "PREPARE_EDITED_STORYBOARD":
            raise PermissionError("Explicit owner storyboard edit confirmation required")
        if set(request) - {"ack", "storyboard"}:
            raise ValueError("Only owner storyboard content is accepted in dashboard")
        from agentforge import media_workflow_v15
        return media_workflow_v15.prepare(
            request.get("storyboard"), confirm_edit=True)
    return UNHANDLED
