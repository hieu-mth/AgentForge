"""Local media/image review and explicit generation approvals."""
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
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
    if path == "/api/visuals/generate-for-website":
        if not server.allow_external_actions:
            raise PermissionError("Local image generation requires external-capable mode")
        if (not isinstance(request, dict)
                or set(request) != {"ack", "slug", "source_sha", "checkpoint"}
                or request.get("ack") != "GENERATE_WEBSITE_VISUAL"):
            raise PermissionError("Explicit Owner website visual generation required")
        from agentforge.features.media import visual_jobs
        from agentforge import product_builder, web_assets
        from hashlib import sha256
        slug = product_builder._check_slug(request["slug"])
        digest = request["source_sha"]
        if (not isinstance(digest, str) or not visual_jobs.SHA.fullmatch(digest)
                or session is None
                or session.get("inspected_visual_websites", {}).get(slug) != digest):
            raise PermissionError("Inspect existing website source before GPU generation")
        project = web_assets._project(slug)
        current = sha256((project / "index.html").read_bytes()).hexdigest()
        if current != digest:
            raise PermissionError("Website changed since inspection")
        topic = visual_jobs.website_subject(slug)
        return visual_jobs.submit(
            "website", topic, [topic], request["checkpoint"],
            confirm_generation=True, source_sha=digest)
    if path.startswith("/api/visuals/") and path.endswith("/attach-website"):
        if (not isinstance(request, dict)
                or set(request) != {"ack", "slug", "image_sha", "html_sha"}
                or request["ack"] != "ATTACH_GENERATED_WEBSITE_IMAGE"):
            raise PermissionError("Explicit SHA-bound website image approval required")
        from agentforge.features.media import visual_jobs
        from agentforge import product_builder
        slug = product_builder._check_slug(request["slug"])
        html_sha, image_sha = request["html_sha"], request["image_sha"]
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid website image route")
        job_id = visual_jobs._id(parts[3])
        if (session is None
                or session.get("inspected_visual_websites", {}).get(slug) != html_sha
                or session.get("reviewed_visual_images", {}).get(job_id) != image_sha):
            raise PermissionError("Inspect website and exact generated image first")
        return visual_jobs.attach_website(
            job_id, slug, image_sha, html_sha, confirm_attach=True)
    if path == "/api/visuals/generate":
        if not server.allow_external_actions:
            raise PermissionError("Local ComfyUI requires external-process mode")
        if (not isinstance(request, dict) or
                set(request) != {"ack", "purpose", "topic", "scenes", "checkpoint"}
                or request.get("ack") != "GENERATE_AI_VISUALS"):
            raise PermissionError("Explicit visual GPU batch approval required")
        from agentforge.features.media import visual_jobs
        return visual_jobs.submit(
            request["purpose"], request["topic"], request["scenes"],
            request["checkpoint"], confirm_generation=True)
    if path == "/api/visuals/generate-for-task":
        if not server.allow_external_actions:
            raise PermissionError("Local ComfyUI requires external-process mode")
        if (not isinstance(request, dict) or
                set(request) != {"ack", "task_id", "source_sha", "checkpoint"}
                or request.get("ack") != "GENERATE_STORYBOARD_VISUALS"):
            raise PermissionError("Explicit reviewed storyboard GPU approval required")
        from agentforge import brain_store, task_history, quality_v14, media_assets
        from agentforge.features.media import visual_jobs
        ident = brain_store._id(request["task_id"])
        digest = request["source_sha"]
        if (not isinstance(digest, str) or not brain_store.SHA.fullmatch(digest)
                or session is None
                or session.get("inspected_storyboard_tasks", {}).get(ident) != digest):
            raise PermissionError("Inspect storyboard before dispatching GPU")
        task = task_history.get_task(ident, db_path=server.task_db_path)
        result = task.get("result")
        if (task.get("status") != "SUCCEEDED"
                or task.get("skill_id") != "media.copy_draft"
                or not isinstance(result, dict)
                or set(result) != {"title", "scenes", "status", "review_required",
                                  "verified_claims"}
                or result.get("status") != "DRAFT_NOT_VERIFIED"
                or result.get("review_required") is not True
                or result.get("verified_claims") is not False
                or quality_v14._sha(result) != digest):
            raise PermissionError("Storyboard was changed or not reviewable")
        scenes = media_assets._scenes(result["scenes"])
        return visual_jobs.submit(
            "video", result["title"],
            [scene["headline"] + ". " + scene["caption"] for scene in scenes],
            request["checkpoint"], confirm_generation=True,
            source_sha=digest)
    if path.startswith("/api/visuals/") and path.endswith("/collect"):
        if not server.allow_external_actions:
            raise PermissionError("Local ComfyUI collection requires external mode")
        if not isinstance(request, dict) or request != {"ack": "IMPORT_AI_VISUAL"}:
            raise PermissionError("Explicit Owner import confirmation required")
        from agentforge.features.media import visual_jobs
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid image job route")
        return visual_jobs.collect(parts[3], confirm_import=True)
    if path == "/api/media/prepare-from-task":
        # Create assets only from a *reviewed* completed task, never from an
        # untrusted editable JSON submitted in this endpoint.
        if (set(request) not in ({"ack", "task_id", "source_sha"},
                                 {"ack", "task_id", "source_sha", "visual_plan"})
                or request.get("ack") != "PREPARE_REVIEWED_STORYBOARD"):
            raise PermissionError("Exact storyboard source and Owner confirmation required")
        from agentforge import brain_store, task_history, quality_v14
        from agentforge.features.media import workflow
        from uuid import uuid4
        ident = brain_store._id(request["task_id"])
        sha = request["source_sha"]
        if not isinstance(sha, str) or not brain_store.SHA.fullmatch(sha):
            raise ValueError("Invalid storyboard SHA")
        if (session is None or
                session.get("inspected_storyboard_tasks", {}).get(ident) != sha):
            raise PermissionError("Inspect the exact storyboard task before producing media")
        task = task_history.get_task(ident, db_path=server.task_db_path)
        if task.get("skill_id") != "media.copy_draft" or task.get("status") != "SUCCEEDED":
            raise PermissionError("Only completed storyboard tasks can prepare media")
        result = task.get("result")
        if not isinstance(result, dict) or set(result) != {
                "title", "scenes", "status", "review_required", "verified_claims"}:
            raise ValueError("Invalid storyboard source")
        if (result["status"] != "DRAFT_NOT_VERIFIED"
                or result["review_required"] is not True
                or result["verified_claims"] is not False
                or quality_v14._sha(result) != sha):
            raise PermissionError("Storyboard provenance or review state mismatch")
        # Workspace requests promise a product video, not text-only slides.
        # Reject missing/Classic visuals before creating a production row.
        # Legacy media.compose and CLI demos can still opt into Classic.
        from agentforge import media_assets
        plan = media_assets.validate_visual_plan(
            request.get("visual_plan"), len(result["scenes"]))
        if plan["mode"] != "studio":
            raise PermissionError(
                "VIDEO_VISUALS_REQUIRED: Need one verified AI image for each scene. "
                "No automatic Classic/template fallback for video requests.")
        # Separate versioned local media output. Never derive a filesystem path
        # or a collision-prone slug from untrusted task content.
        storyboard = {"slug": "video-" + uuid4().hex[:16],
                      "title": result["title"], "scenes": result["scenes"]}
        return workflow.prepare(storyboard, confirm_edit=True,
                                visual_plan=request.get("visual_plan"))
    if path.startswith("/api/videos/") and path.endswith("/render"):
        if not server.allow_external_actions:
            raise PermissionError("Enable explicit local external-process mode to render MP4")
        parts = path.split("/")
        if (len(parts) != 5 or set(request) != {"ack", "storyboard_sha"}
                or request.get("ack") != "RENDER_LOCAL_MP4"):
            raise PermissionError("Explicit SHA-bound local video render approval required")
        from agentforge import brain_store, media_workflow_v15
        ident = brain_store._id(parts[3])
        record = media_workflow_v15._row(ident)
        sha = request["storyboard_sha"]
        if (not isinstance(sha, str) or not brain_store.SHA.fullmatch(sha)
                or sha != record["storyboard_sha"]):
            raise PermissionError("Production storyboard SHA has changed")
        return media_workflow_v15.render(ident, confirm_local_process=True)
    if path == "/api/media/prepare":
        if request.get("ack") != "PREPARE_EDITED_STORYBOARD":
            raise PermissionError("Explicit owner storyboard edit confirmation required")
        if set(request) - {"ack", "storyboard"}:
            raise ValueError("Only owner storyboard content is accepted in dashboard")
        from agentforge import media_workflow_v15
        return media_workflow_v15.prepare(
            request.get("storyboard"), confirm_edit=True)
    return UNHANDLED
