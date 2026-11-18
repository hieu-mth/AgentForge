"""Authenticated, read-only Video Studio routes."""


def dispatch(self, route):
    if route == "/api/characters":
        from agentforge.features.film_studio.characters import list_characters
        return self._reply(200, list_characters())
    if route == "/api/session":
        session = self._session()
        return self._reply(200, {
            "status": "AUTHENTICATED", "csrf": session["csrf"]})
    if route == "/api/publishing":
        from agentforge.features.film_studio.publishing import summary
        return self._reply(200, summary())
    if route.startswith("/api/publishing/"):
        from agentforge.features.film_studio import publishing
        parts = route.split("/")
        if len(parts) not in (4, 5) or parts[:3] != ["", "api", "publishing"]:
            raise ValueError("Invalid release read path")
        rid = parts[3]
        record = publishing.inspect(rid)
        self._session().setdefault("reviewed_publishing", {})[rid] = record["release_sha256"]
        if len(parts) == 5:
            if parts[4] != "handoff":
                raise ValueError("Unknown release operation")
            return self._reply(200, publishing.handoff(rid))
        return self._reply(200, record)
    if route == "/api/video-studio/projects":
        from agentforge.video_projects import list_projects
        return self._reply(200, list_projects())
    if route == "/api/film/productions":
        from agentforge.features.film_studio.production import list_episodes
        return self._reply(200, {
            "episodes": list_episodes(), "auto_gpu_render": False,
            "auto_publish": False, "visual_continuity_verified": False,
        })
    if route.startswith("/api/film/productions/"):
        from agentforge.features.film_studio.production import inspect, inspect_render
        parts = route.split("/")
        if len(parts) != 6 or parts[:4] != ["", "api", "film", "productions"]:
            raise ValueError("Invalid film production path")
        slug, episode = parts[4], parts[5]
        proposal = inspect(episode, slug)
        self._session().setdefault("reviewed_film_productions", {})[
            slug + ":" + episode] = proposal["episode_sha256"]
        result = {"proposal": proposal, "render": None,
                  "visual_continuity_verified": False,
                  "owner_watched": False}
        from agentforge.features.film_studio import production
        if (production._folder(slug, episode, production.FILMS) /
                "render-receipt.json").is_file():
            result["render"] = inspect_render(episode, slug)
        return self._reply(200, result)
    if route == "/api/film/motion":
        from agentforge.features.film_studio.motion_comfy import health
        from agentforge.features.film_studio.motion_verify import list_jobs
        return self._reply(200, {
            "status": "LOCAL_MOTION_PILOT_UNVERIFIED",
            "gpu": health(), "jobs": list_jobs(),
            "model_route_execution": "CONFIG_ONLY",
            "owner_12gb_benchmark_verified": False,
            "automatic_model_download": False, "automatic_upload": False,
        })
    if route.startswith("/api/film/motion/job/"):
        from agentforge.features.film_studio.motion_verify import _job, inspect_receipt
        job_id = route.removeprefix("/api/film/motion/job/")
        from agentforge.features.film_studio.motion_comfy import DB as motion_db
        row = _job(job_id, motion_db)
        session = self._session()
        session.setdefault("reviewed_motion_jobs", {})[job_id] = {
            "plan_sha": row["plan_sha"], "workflow_sha": row["workflow_sha"]}
        result = {"job_id": job_id, "film_slug": row["film_slug"],
                  "shot_id": row["shot_id"], "state": row["state"],
                  "plan_sha": row["plan_sha"], "workflow_sha": row["workflow_sha"],
                  "provider_submitted": row["provider_id"] is not None,
                  "video_accepted": False}
        if row["state"] == "COMPLETE_UNVERIFIED":
            try:
                receipt = inspect_receipt(job_id)
            except KeyError:
                pass
            else:
                result.update({"state": receipt["state"],
                               "clip_sha256": receipt["clip_sha256"],
                               "receipt_sha256": receipt["receipt_sha256"],
                               "technical": receipt["technical"],
                               "owner_reported_peak_vram_gib":
                                   receipt["owner_reported_peak_vram_gib"]})
        return self._reply(200, result)
    if route == "/api/model-hub":
        from agentforge.ai.model_hub import catalog
        return self._reply(200, catalog())
    if route == "/api/ops/discovery":
        from agentforge.ops.discovery import inspect
        return self._reply(200, inspect())
    if route == "/api/ops/preflight":
        from agentforge.ops.preflight import inspect
        return self._reply(200, inspect())
    if route == "/api/visuals/jobs":
        from agentforge.features.media import visual_jobs
        return self._reply(200, visual_jobs.report())
    if route.startswith("/api/visuals/") and route.endswith("/preview"):
        from agentforge.features.media import visual_jobs
        parts = route.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid visual preview route")
        contents, mime = visual_jobs.image_for_job(parts[3])
        from agentforge.features.media.visual_jobs import _row
        self._session().setdefault("reviewed_visual_images", {})[parts[3]] = _row(parts[3])["asset_sha"]
        return self._reply(200, contents, mime=mime)
    if route == "/api/media/studio-images":
        # Film Studio only: report already imported generic image/video jobs.
        # Inventory only; no network or GPU activity from this GET.
        from agentforge.features.media import visual_jobs
        rows = visual_jobs.report()["jobs"]
        images = [{
            "job_id": row["job_id"], "source": "AI " + row["purpose"],
            "sha256": row["asset_sha"],
            "preview_url": "/api/visuals/" + row["job_id"] + "/preview",
        } for row in rows
            if row.get("status") == "ASSET_READY"
            and row.get("purpose") in {"video", "image"}
            and row.get("asset_sha")]
        return self._reply(200, {"images": images[:80],
                                 "generation_started": False,
                                 "require_distinct_images": True})
    return self._blocked(404, "not_found")
