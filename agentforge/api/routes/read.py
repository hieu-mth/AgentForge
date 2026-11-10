"""Authenticated read-only API routing; no new public endpoints."""
from agentforge import analytics_store, brain_runner, brain_store, growth_reports
from agentforge import growth_store, task_history
from agentforge.core import artifact_acceptance
from agentforge.api.routes.bootstrap import _public_task, _summary


def dispatch(self, route):
    if route == "/api/session":
        session = self._session()
        return self._reply(200, {
            "status": "AUTHENTICATED", "csrf": session["csrf"]})
    if route == "/api/bootstrap":
        return self._reply(200, _summary(self.server))
    if route.startswith("/api/image/") and route.endswith("/preview"):
        from agentforge.asset_preview import image_for_job
        job_id = route[len("/api/image/"):-len("/preview")]
        content, image_type = image_for_job(job_id)
        return self._reply(200, content, mime=image_type)
    if route == "/api/image/health":
        from agentforge.image_studio_v24 import health
        return self._reply(200, health())
    if route == "/api/image/jobs":
        from agentforge.image_studio_v24 import report
        return self._reply(200, report())
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
            "S5 growth": self.server.growth_db_path or growth_store.DB,
        }
        return self._reply(200, ops_doctor.inspect(
            paths=source_paths, task_db=self.server.task_db_path,
            brain_db=self.server.brain_db_path))
    if route == "/api/memory":
        return self._reply(200, brain_store.list_memory(
            db_path=self.server.brain_db_path))
    if route.startswith("/api/webapps/qa/"):
        from agentforge.features.webapps import browser_qa
        parts = route.split("/")
        if (len(parts) != 7 or parts[:4] != ["", "api", "webapps", "qa"]
                or parts[6] not in {"desktop.png", "mobile.png"}):
            raise ValueError("Invalid browser QA image route")
        report_id, report_sha, filename = parts[4], parts[5], parts[6]
        report = browser_qa.read_report(report_id, report_sha)
        if self._session().get("reviewed_webapps", {}).get(
                report["proposal_id"]) != report["source_sha256"]:
            raise PermissionError("Review this signed React proposal before viewing QA screenshot")
        return self._reply(200, browser_qa.image(report_id, report_sha, filename),
                           mime="image/png")
    if route.startswith("/api/webapps/") and route.endswith("/export"):
        from agentforge.features.webapps.exporter import create_zip
        from agentforge import webapp_developer
        parts = route.split("/")
        if len(parts) != 5 or parts[1:3] != ["api", "webapps"]:
            raise ValueError("Invalid webapp export route")
        pid = parts[3]
        provider = webapp_developer.provider(pid)
        info = provider.inspect(pid)
        if self._session().get("reviewed_webapps", {}).get(pid) != info["sha256"]:
            raise PermissionError("Review exact source SHA before export")
        record = create_zip(pid, info["sha256"])
        return self._reply(200, record["data"], mime="application/zip",
                           headers=(("Content-Disposition",
                                     'attachment; filename="' + record["filename"] + '"'),
                                    ("X-Archive-SHA256", record["zip_sha256"]),
                                    ("X-Source-SHA256", info["sha256"])))
    if route.startswith("/api/webapps/"):
        from agentforge import webapp_developer
        parts = route.split("/")
        if len(parts) != 4 or parts[1:3] != ["api", "webapps"]:
            raise ValueError("Invalid application review route")
        proposal_id = parts[3]
        provider = webapp_developer.provider(proposal_id)
        document, _ = provider._read_proposal(proposal_id)
        session = self._session()
        session.setdefault("reviewed_webapps", {})[proposal_id] = document["sha256"]
        comparison = provider.compare(proposal_id)
        return self._reply(200, {
            "proposal_id": proposal_id,
            "sha256": document["sha256"],
            "project_slug": document["project_slug"],
            "status": document["status"],
            "format": document["format"],
            "revision": document.get("revision"),
            "comparison": comparison,
            "ai_code_experimental": provider is not webapp_developer.base,
            "artifact_acceptance": artifact_acceptance.inspect(
                    proposal_id, document["sha256"], db_path=self.server.task_db_path),
            "files": [{"path": file["path"], "content": file["content"]}
                      for file in document["files"]],
            "execution_authorized": False,
            "deployment_authorized": False,
        })
    if route.startswith("/api/proposals/") and route.endswith("/preview"):
        from agentforge.website_preview import from_proposal
        ident = route[len("/api/proposals/"):-len("/preview")]
        page = from_proposal(ident)
        return self._reply(200, page, mime="text/html; charset=utf-8",
                           isolated_preview=True)
    if route.startswith("/api/proposals/"):
        from agentforge import product_builder
        ident = route.removeprefix("/api/proposals/")
        document, _ = product_builder._read_proposal(ident)
        if document["status"] != "PROPOSED_NOT_APPLIED":
            raise ValueError("Proposal cannot be reviewed")
        session = self._session()
        session.setdefault("reviewed_proposals", {})[ident] = document["sha256"]
        return self._reply(200, {
            "proposal_id": ident, "project_slug": document["project_slug"],
            "sha256": document["sha256"],
            "status": document["status"],
            "summary": document["summary"],
            "artifact_acceptance": artifact_acceptance.inspect(
                    ident, document["sha256"], "proposals", db_path=self.server.task_db_path),
            "files": [{"path": f["path"], "content": f["content"]}
                      for f in document["files"]],
            "execution_authorized": False,
        })
    if route.startswith("/api/videos/"):
        from agentforge import media_workflow_v15, media_quality
        ident = route.removeprefix("/api/videos/")
        record = media_workflow_v15._row(ident)
        if record["status"] != "VIDEO_READY":
            raise PermissionError("Only completed MP4 can be reviewed")
        _, manifest = media_workflow_v15._verify_storyboard_manifest(record)
        qa = media_quality.check(record["run_id"])
        if (qa["status"] != "VIDEO_PASS" or qa["failures"] or
                not qa["video_verified"] or
                manifest["artifacts"].get("video.mp4") != record["video_sha"]):
            raise PermissionError("MP4 integrity/quality is not verified")
        self._session().setdefault("inspected_video", {})[ident] = record["video_sha"]
        return self._reply(200, {
            "production_id": ident, "run_id": record["run_id"],
            "video_sha": record["video_sha"], "quality": qa["status"],
            "relative_path": "workspace/media/" + record["run_id"] + "/video.mp4",
            "published": False, "review_requires_playback": True})
    if route.startswith("/api/drafts/"):
        from agentforge import quality_v14
        ident = route.removeprefix("/api/drafts/")
        from agentforge import brain_store
        brain_store._id(ident)
        found = next((item for item in quality_v14.inbox()["reviews"]
                      if item["job_id"] == ident), None)
        if found is None:
            raise KeyError("Draft not found")
        task = task_history.get_task(found["task_id"], db_path=self.server.task_db_path)
        if (task.get("status") != "SUCCEEDED" or
                task.get("skill_id") != "media.copy_draft" or
                found["skill_id"] != "media.copy_draft"):
            raise PermissionError("Only bounded storyboard drafts can be inspected")
        result = task.get("result")
        if (not isinstance(result, dict) or
                len(quality_v14._canonical(result).encode("utf-8")) > 65000 or
                quality_v14._sha(result) != found["output_sha"]):
            raise PermissionError("Storyboard result digest mismatch")
        # Read-only review: model data displayed as text, never executed.
        session = self._session()
        session.setdefault("reviewed_ai_drafts", {})[ident] = found["output_sha"]
        return self._reply(200, {
            "job_id": ident, "output_sha": found["output_sha"],
            "quality": found["quality"], "decision": found["decision"],
            "task": _public_task(task),
            "storyboard": result})
    if route.startswith("/api/goals/"):
        ident = route.removeprefix("/api/goals/")
        return self._reply(200, brain_runner.inspect(
            ident, brain_db_path=self.server.brain_db_path, task_db_path=self.server.task_db_path))
    if route.startswith("/api/tasks/"):
        ident = route.removeprefix("/api/tasks/")
        task = task_history.get_task(ident, db_path=self.server.task_db_path)
        return self._reply(200, {
            **_public_task(task, db_path=self.server.task_db_path),
            "events": [{"at": x["at"], "name": x["name"]}
                       for x in task["events"]]})
    if route.startswith("/api/growth/"):
        return self._reply(200, growth_reports.report(
            route.removeprefix("/api/growth/"),
            db_path=self.server.growth_db_path))
    return self._blocked(404, "not_found")
