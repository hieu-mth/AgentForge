"""Authenticated, read-only Video Studio routes."""


def dispatch(self, route):
    if route == "/api/ops/comfyui":
        import sqlite3
        from agentforge.integrations import comfy_service
        try:
            status = comfy_service.status()
        except sqlite3.Error:
            return self._blocked(503, "comfy_service_storage_unavailable")
        return self._reply(200, {**status, "can_manage": self.server.allow_external_actions})
    if route == "/api/film/drafts/resources":
        from agentforge.features.film_studio import draft_resources
        return self._reply(200, draft_resources.snapshot())
    if route == "/api/film/drafts":
        from agentforge.features.film_studio import draft_pipeline
        return self._reply(200, {"drafts": [draft_pipeline.public_view(job) for job in draft_pipeline.list_drafts()]})
    if route.startswith("/api/film/drafts/"):
        from agentforge.features.film_studio import draft_pipeline
        from agentforge.api.routes.film_preview import _serve
        parts = route.split("/")
        if len(parts) not in {5, 6}:
            raise ValueError("Invalid draft route")
        job = draft_pipeline._read(parts[4])
        if len(parts) == 5:
            return self._reply(200, draft_pipeline.public_view(job))
        if parts[5] == "cloud-jobs":
            from agentforge.features.film_studio import draft_motion_cloud
            return self._reply(200, {"jobs": draft_motion_cloud.reconciliation_jobs(job)})
        if parts[5] == "preview":
            def verify(stream):
                draft_pipeline.verify_video(job, stream)
                self._session().setdefault("draft_previews", {})[job["id"]] = job["video_sha"]
            return _serve(self, draft_pipeline.video_path(job), draft_pipeline.MAX_VIDEO, "draft.mp4", verify)
        if parts[5] == "receipt":
            return self._reply(200, draft_pipeline.verified_receipt(job), mime="application/json",
                               headers=(("Content-Disposition", 'attachment; filename="draft.receipt.json"'),))
        if parts[5] == "captions" and job.get("subtitle_sha"):
            from agentforge.features.film_studio import draft_timeline
            draft_pipeline.verified_receipt(job)
            captions = draft_timeline.captions(job["board"]["scenes"], draft_timeline.job_fps(job))
            if draft_pipeline._sha(captions) != job["subtitle_sha"]:
                raise ValueError("Draft subtitle hash mismatch")
            return self._reply(200, captions, mime="application/x-subrip",
                               headers=(("Content-Disposition", 'attachment; filename="captions.srt"'),))
        if parts[5].startswith("scene-") and parts[5][6:].isascii() and parts[5][6:].isdecimal():
            return self._reply(200, draft_pipeline.image(job, int(parts[5][6:])), mime="image/png")
        if parts[5].startswith("motion-") and parts[5][7:].isascii() and parts[5][7:].isdecimal():
            from agentforge.features.film_studio import studio_runtime
            scenes = job.get("board", {}).get("scenes", [])
            index = draft_pipeline._number(int(parts[5][7:]), 0, len(scenes)-1)
            scene = scenes[index]
            if not scene.get("motion_sha"):
                return self._blocked(404, "film_preview_unavailable")

            motion = studio_runtime.motion_artifacts(job)
            return _serve(self, motion.clip_path(scene), motion.MAX_CLIP_BYTES, "motion.mp4",
                          lambda stream: motion.verify_clip(scene, stream))
        raise ValueError("Invalid draft asset route")
    if route == "/api/characters":
        from agentforge.features.film_studio.character_references import library
        return self._reply(200, library())
    if route.startswith("/api/characters/"):
        from agentforge.features.film_studio import character_references
        parts = route.split("/")
        if len(parts) == 5 and parts[4] == "references":
            return self._reply(200, character_references.list_packs(parts[3]))
        if len(parts) == 7 and parts[4] == "references" and parts[5].isascii() and parts[5].isdecimal():
            payload, mime = character_references.image_bytes(parts[3], int(parts[5]), parts[6])
            return self._reply(200, payload, mime=mime)
        raise ValueError("Invalid character reference route")
    if route == "/api/session":
        session = self._session()
        return self._reply(200, {
            "status": "AUTHENTICATED", "csrf": session["csrf"]})
    if route == "/api/publishing":
        from agentforge.features.film_studio.publishing import summary
        return self._reply(200, summary())
    if route.startswith("/api/publishing/draft/"):
        from agentforge.features.film_studio import publishing
        parts = route.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid Studio publishing source")
        source = publishing.draft_source(parts[4])
        self._session().setdefault("reviewed_draft_releases", {})[parts[4]] = (
            source["episode_sha256"], source["receipt_sha256"])
        return self._reply(200, {key: value for key, value in source.items() if key != "video_file"})
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
        parts = route.split("/")
        if len(parts) == 7 and parts[-1] == "preview":
            from agentforge.api.routes.film_preview import preview
            return preview(self, parts[4], parts[5])
        from agentforge.features.film_studio.production import inspect, inspect_render
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
        parts = route.split("/")
        if len(parts) == 7 and parts[-1] == "preview":
            from agentforge.api.routes.film_preview import clip_preview
            return clip_preview(self, parts[5])
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
    if route.startswith("/api/model-hub/media-probe/") and route.endswith("/local-preview"):
        from agentforge.features.film_studio import media_probe
        from agentforge.api.routes.film_preview import _serve
        parts = route.split("/")
        if len(parts) != 6:
            raise ValueError("Invalid local media probe preview route")
        receipt = media_probe.local_video_record(parts[4])
        return _serve(self, media_probe.local_video_path(receipt), media_probe.MAX_VIDEO, "probe.mp4",
                      lambda stream: media_probe.verify_local_video(receipt, stream))
    if route.startswith("/api/model-hub/media-probe/") and route.endswith("/preview"):
        from agentforge.features.film_studio import media_probe
        from agentforge.api.routes.film_preview import _serve
        parts = route.split("/")
        if len(parts) != 6:
            raise ValueError("Invalid media probe preview route")
        row = media_probe.video_record(parts[4])
        return _serve(self, media_probe.video_path(row), media_probe.MAX_VIDEO, "probe.mp4",
                      lambda stream: media_probe.verify_video(row, stream))
    if route == "/api/visuals/jobs":
        from agentforge.features.media import visual_jobs
        return self._reply(200, visual_jobs.report())
    if route.startswith("/api/visuals/") and route.endswith("/details"):
        from agentforge.features.media import visual_jobs
        parts = route.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid visual job route")
        row = visual_jobs._row(parts[3])
        return self._reply(200, {**row, "runtime": visual_jobs.runtime_details(parts[3])})
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
            and not row.get("probe")
            and row.get("purpose") in {"video", "image"}
            and row.get("asset_sha")]
        return self._reply(200, {"images": images[:80],
                                 "generation_started": False,
                                 "require_distinct_images": True})
    return self._blocked(404, "not_found")
