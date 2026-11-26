"""Local media/image review and explicit generation approvals."""
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path == "/api/film/drafts/start":
        required = {"id", "idea", "seconds", "ratio", "scene_count"}
        if not server.allow_external_actions or request.keys() not in (
                required, required | {"mode"}, required | {"mode", "motion_approved"},
                required | {"mode", "duration_mode"},
                required | {"mode", "duration_mode", "route_strategy", "max_cloud_seconds"}):
            raise PermissionError("Draft production requires external-tools mode and a complete brief")
        from agentforge.features.film_studio import draft_pipeline
        return draft_pipeline.submit(request)
    if path.startswith("/api/film/drafts/"):
        parts = path.split("/")
        storyboard = {
            "storyboard-approve": {"sha256"},
            "storyboard-edit": {"sha256", "index", "description", "image_prompt", "motion_prompt"},
            "storyboard-add": {"sha256", "index", "description", "image_prompt", "motion_prompt"},
            "storyboard-remove": {"sha256", "index"},
            "storyboard-move": {"sha256", "index", "target"},
            "storyboard-rewrite": {"sha256", "index", "feedback"},
            "storyboard-regenerate": {"sha256", "index", "scope"},
            "storyboard-quality-repair": {"sha256", "video_sha", "max_repairs", "allow_cloud"},
            "storyboard-duration": {"sha256", "seconds"},
            "storyboard-audio": {"sha256", "engine", "voice_name"},
            "storyboard-audio-direct": {"sha256", "engine", "voice_name", "voices"},
            "storyboard-continuity": {"sha256"},
        }
        if len(parts) != 6 or parts[5] not in {"approve", "reject", "edit", "resume", "cancel", "delete", "visual-review", "visual-review-batch", "cloud-reconcile", *storyboard}:
            raise ValueError("Unknown draft action")
        from agentforge.features.film_studio import draft_pipeline
        identifier, action = parts[4:]
        if action in {"resume", "storyboard-approve", "storyboard-rewrite", "storyboard-continuity", "storyboard-audio-direct", "storyboard-quality-repair", "visual-review", "visual-review-batch", "cloud-reconcile"} and not server.allow_external_actions:
            raise PermissionError("Draft production requires external-tools mode")
        required = {"sha256"} if action in {"approve", "reject"} else (
            {"index", "description", "image_prompt"} if action == "edit" else storyboard.get(action, set()))
        if action == "cloud-reconcile":
            required = {"sha256", "motion_job", "provider_id", "request_sha", "owner_matched"}
        if action == "visual-review":
            required = {"sha256", "video_sha", "index", "allow_cloud"}
        if action == "visual-review-batch":
            required = {"sha256", "video_sha", "max_reviews", "allow_cloud"}
        optional = {"caption", "scene_notes"} if action in {"storyboard-edit", "storyboard-add"} else set()
        if action == "storyboard-audio-direct":
            optional = {"generate_audio"}
        if action == "resume":
            optional = {"retry_motion_job"}
        if not required <= request.keys() <= required | optional:
            raise ValueError("Invalid draft action fields")
        if action in {"approve", "reject"}:
            draft_pipeline._read(identifier)
            if (session is None or not isinstance(request["sha256"], str)
                    or session.get("draft_previews", {}).get(identifier) != request["sha256"]):
                raise PermissionError("Preview the current draft before reviewing")
        result = draft_pipeline.act(identifier, action, request)
        if action == "storyboard-approve":
            draft_pipeline._dispatch()
            return draft_pipeline._read(identifier)
        return result
    if path in {"/api/film/productions/render", "/api/film/productions/voice"}:
        if not server.allow_external_actions:
            raise PermissionError("Explicit Owner external-process mode required")
        from agentforge.features.film_studio import production
        from agentforge import ops_control
        ops_control.require_active()
        action = "render" if path.endswith("/render") else "voice"
        mandatory = {"ack", "film_slug", "episode_id", "episode_sha"}
        expected = mandatory if action == "render" else mandatory | {"engine", "voice_name"}
        if not isinstance(request, dict) or set(request) != expected:
            raise ValueError("Unexpected film production action fields")
        if request["ack"] != ("ASSEMBLE_LOCAL_FILM" if action == "render"
                              else "SYNTHESIZE_LOCAL_VOICE"):
            raise PermissionError("Explicit film production consent required")
        slug, ident, sha = request["film_slug"], request["episode_id"], request["episode_sha"]
        key = (slug + ":" + ident) if isinstance(slug, str) and isinstance(ident, str) else ""
        if session is None or session.get("reviewed_film_productions", {}).get(key) != sha:
            raise PermissionError("Inspect exact episode SHA before producing output")
        if action == "render":
            return production.render(ident, slug, sha, confirmed=True)
        if request["engine"] not in {"windows", "piper"}:
            raise ValueError("Unsupported offline TTS engine")
        return production.voice(ident, slug, sha, engine=request["engine"],
                                voice_name=request["voice_name"], confirmed=True)
    if path in {"/api/film/motion/poll", "/api/film/motion/collect"}:
        if not server.allow_external_actions:
            raise PermissionError("Film runtime requires explicit external-capable Owner mode")
        from agentforge.features.film_studio.motion_verify import _job
        from agentforge.features.film_studio.motion_comfy import DB as motion_db
        from agentforge import ops_control
        ops_control.require_active()
        action = "poll" if path.endswith("/poll") else "collect"
        expected = ({"ack", "job_id", "plan_sha", "workflow_sha"} if action == "poll"
                    else {"ack", "job_id", "plan_sha", "workflow_sha", "filename"})
        if not isinstance(request, dict) or set(request) != expected:
            raise ValueError("Invalid motion action fields")
        if request.get("ack") != ("CHECK_LOCAL_COMFY_HISTORY" if action == "poll"
                                else "IMPORT_LOCAL_COMFY_MP4"):
            raise PermissionError("Owner must explicitly confirm motion action")
        job_id = request["job_id"]
        row = _job(job_id, motion_db)
        pair = {"plan_sha": row["plan_sha"], "workflow_sha": row["workflow_sha"]}
        if (session is None or session.get("reviewed_motion_jobs", {}).get(job_id) != pair
                or request["plan_sha"] != row["plan_sha"]
                or request["workflow_sha"] != row["workflow_sha"]):
            raise PermissionError("Inspect the exact motion job before acting")
        if action == "poll":
            from agentforge.features.film_studio.motion_comfy import job_status
            return job_status(job_id)
        import os
        from pathlib import Path
        from agentforge.features.film_studio.motion_verify import import_clip
        folder = os.environ.get("AGENTFORGE_COMFY_OUTPUT_DIR")
        if not folder:
            raise ValueError("Owner must configure local ComfyUI output directory")
        return import_clip(
            job_id=job_id, filename=request["filename"], output_dir=Path(folder),
            confirmed=True)
    if path == "/api/visuals/flux":
        if not server.allow_external_actions:
            raise PermissionError("Local ComfyUI requires external-tools mode")
        options = {"width", "height", "steps", "seed", "scene"}
        if (set(request) - options not in ({"prompt"}, {"prompt", "ack"})
                or ("ack" in request and request["ack"] != "GENERATE_AI_VISUALS")):
            raise ValueError("Invalid FLUX image request")
        from agentforge.features.media import flux_runtime
        from agentforge.ai.model_hub import local_inference_slot
        with local_inference_slot():
            return flux_runtime.generate(request["prompt"], automated="ack" not in request,
                                         **{key: request[key] for key in options & request.keys()})
    if path == "/api/visuals/approve":
        if (set(request) != {"job_id", "sha256"} or session is None
                or not isinstance(request["job_id"], str)
                or session.get("reviewed_visual_images", {}).get(request["job_id"]) != request["sha256"]):
            raise PermissionError("Preview the exact image before approving")
        from agentforge.features.media import visual_jobs
        return visual_jobs.approve(request["job_id"], request["sha256"])
    if path == "/api/visuals/generate":
        if not server.allow_external_actions:
            raise PermissionError("Local ComfyUI requires external-process mode")
        if (not isinstance(request, dict) or
                set(request) != {"ack", "purpose", "topic", "scenes", "checkpoint"}
                or request.get("ack") != "GENERATE_AI_VISUALS"):
            raise PermissionError("Explicit visual GPU batch approval required")
        from agentforge.ai.model_hub import local_inference_slot
        from agentforge.features.film_studio import draft_resources
        from agentforge.features.media import visual_jobs
        from agentforge.integrations import comfy_service, comfyui
        with local_inference_slot():
            draft_resources.require_gpu("image")
            comfy_service.require_other_queue_idle(comfyui.DEFAULT_PORT)
            comfy_service.require_idle_queue(comfyui.DEFAULT_PORT)
            return visual_jobs.submit(
                request["purpose"], request["topic"], request["scenes"],
                request["checkpoint"], confirm_generation=True)
    if path.startswith("/api/visuals/") and path.endswith("/collect"):
        if not server.allow_external_actions:
            raise PermissionError("Local ComfyUI collection requires external mode")
        if not isinstance(request, dict) or request != {"ack": "IMPORT_AI_VISUAL"}:
            raise PermissionError("Explicit Owner import confirmation required")
        from agentforge.features.media import visual_jobs
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid image job route")
        from agentforge.ai.model_hub import local_inference_slot
        with local_inference_slot():
            return visual_jobs.collect(parts[3], confirm_import=True)
    return UNHANDLED
