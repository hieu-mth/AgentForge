"""Authenticated read-only API routing; no new public endpoints."""
from agentforge import analytics_store, brain_runner, brain_store
from agentforge import task_history
from agentforge.core import artifact_acceptance
from agentforge.api.routes.bootstrap import _public_task, _summary


def dispatch(self, route):
    if route.startswith("/api/artifacts/reports/"):
        ident = route.removeprefix("/api/artifacts/reports/")
        task = task_history.get_task(ident, db_path=self.server.task_db_path)
        result = task["result"]
        if not isinstance(result, dict):
            raise ValueError("Report receipt unavailable")
        sha = result.get("sha256")
        doc, _ = artifact_acceptance.source(ident, sha, "reports", db_path=self.server.task_db_path)
        acceptance = artifact_acceptance.inspect(ident, sha, "reports", db_path=self.server.task_db_path)
        self._session().setdefault("reviewed_reports", {})[ident] = sha
        return self._reply(200, {**doc, "proposal_id": ident,
                                 "artifact_acceptance": acceptance})
    if route == "/api/characters":
        from agentforge.features.film_studio.characters import list_characters
        return self._reply(200, list_characters())
    if route == "/api/session":
        session = self._session()
        return self._reply(200, {
            "status": "AUTHENTICATED", "csrf": session["csrf"]})
    if route == "/api/bootstrap":
        return self._reply(200, _summary(self.server))
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
    if route == "/api/model/health":
        from agentforge.model_health import check
        return self._reply(200, check())
    if route == "/api/retention/inventory":
        from agentforge.storage import retention
        return self._reply(200, retention.inventory())
    if route == "/api/retention/backups":
        from agentforge.storage import retention
        return self._reply(200, retention.list_backups())
    if route.startswith("/api/retention/inspect/"):
        from agentforge.storage import retention
        pieces = route.split("/")
        if len(pieces) != 6 or pieces[1:4] != ["api", "retention", "inspect"]:
            raise ValueError("Invalid artifact inspection route")
        inspected = retention.inspect(pieces[4], pieces[5])
        session = self._session()
        session.setdefault("inspected_artifacts", {})[(pieces[4], pieces[5])] = inspected["tree_sha256"]
        return self._reply(200, inspected)
    if route.startswith("/api/retention/verify/"):
        from agentforge.storage import retention
        pieces = route.split("/")
        if len(pieces) != 5 or pieces[1:4] != ["api", "retention", "verify"]:
            raise ValueError("Invalid backup verification route")
        verified = retention.verify(pieces[4])
        session = self._session()
        session.setdefault("verified_artifact_backups", {})[pieces[4]] = verified["tree_sha256"]
        return self._reply(200, verified)
    if route == "/api/artifacts":
        from agentforge.artifact_catalog import report
        return self._reply(200, report())
    if route == "/api/workforce":
        from agentforge.ai.workforce import inspect
        return self._reply(200, inspect(brain_db_path=self.server.brain_db_path,
                                        task_db_path=self.server.task_db_path))
    if route == "/api/ops/discovery":
        from agentforge.ops.discovery import inspect
        return self._reply(200, inspect())
    if route == "/api/ops/preflight":
        from agentforge.ops.preflight import inspect
        return self._reply(200, inspect())
    if route == "/api/ops/acceptance":
        from agentforge.ops.base_acceptance import inspect
        return self._reply(200, inspect())
    if route == "/api/ops/health":
        from agentforge import ops_doctor
        source_paths = {
            "S1 tasks": self.server.task_db_path or task_history.DEFAULT_DB,
            "S3 analytics": self.server.analytics_db_path or analytics_store.DB,
            "S4 goals": self.server.brain_db_path or brain_store.DB,
        }
        return self._reply(200, ops_doctor.inspect(
            paths=source_paths, task_db=self.server.task_db_path,
            brain_db=self.server.brain_db_path))
    if route == "/api/memory":
        return self._reply(200, brain_store.list_memory(
            db_path=self.server.brain_db_path))
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
        # No Website Builder DB reads, network calls, or GPU execution.
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
    if route.startswith("/api/goals/") and route.endswith("/capabilities"):
        from agentforge.ai.model_health import inspect_goal_step
        ident = route.removeprefix("/api/goals/").removesuffix("/capabilities")
        goal = brain_store.get_goal(ident, db_path=self.server.brain_db_path)
        return self._reply(200, inspect_goal_step(goal))
    if route.startswith("/api/goals/"):
        ident = route.removeprefix("/api/goals/")
        return self._reply(200, brain_runner.inspect(
            ident, brain_db_path=self.server.brain_db_path, task_db_path=self.server.task_db_path))
    if route.startswith("/api/tasks/"):
        ident = route.removeprefix("/api/tasks/")
        task = task_history.get_task(ident, db_path=self.server.task_db_path)
        return self._reply(200, {
            **_public_task(task, db_path=self.server.task_db_path),
            "storyboard_source_sha": None,
            "events": [{"at": x["at"], "name": x["name"]}
                       for x in task["events"]]})
    return self._blocked(404, "not_found")
