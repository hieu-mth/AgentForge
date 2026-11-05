"""S1 allowlisted skill adapters; explicit per-call grants and durable results.

This is a local owner CLI, not OS isolation or multi-user authentication.
"""
import argparse
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from agentforge import skill_registry as registry
from agentforge import task_history as history

# Code-level policy: manifests cannot silently remove required grants.
POLICY = {
    "web.quality_check": ("product_builder", "read_only",
                          frozenset({"workspace.read"})),
    "web.create": ("product_builder", "owner_gated",
                   frozenset({"model.invoke", "workspace.propose"})),
    "web.browser_test": ("product_builder", "owner_gated",
                         frozenset({"workspace.read", "browser.run"})),
    "research.opportunity": ("opportunity_researcher", "owner_gated",
                             frozenset({"model.invoke", "network.search", "workspace.write"})),
    "research.source_review": ("source_reviewer", "owner_gated",
                               frozenset({"workspace.read", "workspace.write",
                                          "model.invoke", "network.read"})),
    "media.compose": ("media_producer", "owner_gated",
                      frozenset({"workspace.write"})),
    "media.image_edit": ("media_producer", "owner_gated",
                         frozenset({"workspace.write"})),
    "media.quality_check": ("media_producer", "read_only",
                            frozenset({"workspace.read"})),
    "media.video_render": ("media_producer", "owner_gated",
                           frozenset({"workspace.write", "process.run"})),
    "media.tts": ("media_producer", "owner_gated",
                  frozenset({"workspace.write", "process.run"})),
    "media.copy_draft": ("media_producer", "owner_gated",
                         frozenset({"model.invoke", "workspace.propose"})),
    "analytics.import": ("analytics_analyst", "owner_gated",
                         frozenset({"workspace.write"})),
    "analytics.quality_check": ("analytics_analyst", "read_only",
                                frozenset({"workspace.read"})),
    "analytics.content_report": ("analytics_analyst", "read_only",
                                 frozenset({"workspace.read"})),
    "analytics.trend_report": ("analytics_analyst", "read_only",
                               frozenset({"workspace.read"})),
    "analytics.experiment_report": ("analytics_analyst", "read_only",
                                    frozenset({"workspace.read"})),
    "analytics.finance_report": ("analytics_analyst", "read_only",
                                 frozenset({"workspace.read"})),
    "analytics.opportunity_score": ("analytics_analyst", "read_only",
                                    frozenset({"workspace.read"})),
    "growth.campaign_create": ("growth_operator", "owner_gated",
                               frozenset({"workspace.write"})),
    "growth.bundle_prepare": ("growth_operator", "owner_gated",
                              frozenset({"workspace.write"})),
    "growth.record_event": ("growth_operator", "owner_gated",
                            frozenset({"workspace.write"})),
    "growth.report": ("growth_operator", "read_only",
                      frozenset({"workspace.read"})),
    "growth.quality_check": ("growth_operator", "read_only",
                             frozenset({"workspace.read"})),
    "growth.reconcile": ("growth_operator", "read_only",
                         frozenset({"workspace.read"})),
}


def _contract(skill_id):
    if skill_id not in POLICY:
        raise PermissionError("Skill has no trusted adapter")
    skill = registry.load_skill(skill_id)
    worker, mode, grants = POLICY[skill_id]
    if (skill["worker_id"] != worker or skill["execution_mode"] != mode
            or set(skill["required_permissions"]) != grants):
        raise PermissionError("Manifest differs from fixed adapter policy")
    return skill, grants


def missing_grants(skill_id, granted=(), *, confirm_model_call=False,
                   confirm_browser_run=False, confirm_external_run=False,
                   payload=None):
    _, needed = _contract(skill_id)
    granted = frozenset(granted)
    if not granted.issubset(registry.PERMISSIONS):
        raise PermissionError("Unknown permission grant")
    missing = set(needed - (granted | {"workspace.read"}))
    if "model.invoke" in needed and confirm_model_call is not True:
        missing.add("confirm_model_call")
    if "browser.run" in needed and confirm_browser_run is not True:
        missing.add("confirm_browser_run")
    if skill_id == "web.browser_test" and (
        not isinstance(payload, dict) or payload.get("confirm_browser_run") is not True
    ):
        missing.add("input.confirm_browser_run")
    if skill_id == "research.source_review" and (
        not isinstance(payload, dict) or payload.get("approve_read_only") is not True
    ):
        missing.add("input.approve_read_only")
    if "process.run" in needed:
        if confirm_external_run is not True:
            missing.add("confirm_external_run")
        if not isinstance(payload, dict) or payload.get("confirm_external_run") is not True:
            missing.add("input.confirm_external_run")
    if skill_id == "analytics.import" and (
        not isinstance(payload, dict) or payload.get("confirm_write") is not True
    ):
        missing.add("input.confirm_write")
    if skill_id in {"growth.campaign_create", "growth.bundle_prepare", "growth.record_event"}:
        if not isinstance(payload, dict) or payload.get("confirm_write") is not True:
            missing.add("input.confirm_write")
    if skill_id == "growth.bundle_prepare" and (
        not isinstance(payload, dict) or payload.get("confirm_rights") is not True
    ):
        missing.add("input.confirm_rights")
    if skill_id == "growth.record_event" and isinstance(payload, dict):
        if payload.get("kind") == "post_attest" and (
            not isinstance(payload.get("data"), dict)
            or payload["data"].get("confirm_owner_posted") is not True
        ):
            missing.add("input.confirm_owner_posted")
    return sorted(missing)


def _dispatch(skill_id, payload):
    if skill_id == "web.quality_check":
        from agentforge.product_quality import check_project
        return check_project(payload["slug"])
    if skill_id == "web.create":
        from agentforge.product_builder import propose
        return propose(payload["slug"], payload["brief"])
    if skill_id == "web.browser_test":
        from agentforge.browser_validation import validate
        return validate("project", payload["slug"], confirm_browser_run=True,
                        browser_channel=payload.get("browser_channel", "msedge"))
    if skill_id == "research.opportunity":
        from agentforge.research import run
        with redirect_stdout(StringIO()):
            return run(payload["topic"])
    if skill_id == "research.source_review":
        from agentforge.source_review import run_review
        with redirect_stdout(StringIO()):
            return run_review(payload["task_id"], payload["allowed_hosts"],
                              max_pages=payload.get("max_pages", 4),
                              approve_read_only=True)
    if skill_id == "media.compose":
        from agentforge.media_assets import make_assets
        return make_assets(payload)
    if skill_id == "media.quality_check":
        from agentforge.media_quality import check
        return check(payload["run_id"])
    if skill_id == "media.image_edit":
        from agentforge.media_quality import edit_image
        return edit_image(payload["run_id"], payload["scene_index"], payload["operation"])
    if skill_id == "media.video_render":
        from agentforge.media_render import render_video
        return render_video(payload["run_id"], confirm_external_run=True)
    if skill_id == "media.tts":
        from agentforge.media_render import make_voiceover
        return make_voiceover(payload["run_id"], payload["engine"],
                              voice=payload.get("voice"), confirm_external_run=True)
    if skill_id == "media.copy_draft":
        from agentforge.media_pipeline import suggest_copy
        return suggest_copy(payload["topic"], payload["audience"], payload["goal"])
    if skill_id == "analytics.import":
        from agentforge.analytics_store import import_csv
        return import_csv(payload["dataset"], payload["kind"], payload["filename"],
                          source_kind=payload["source_kind"],
                          synthetic=payload["synthetic"], confirm_write=True)
    if skill_id == "web.create":
        # Stable categories only: NEVER include model text, local paths or tokens.
        import socket
        from urllib.error import HTTPError, URLError
        if isinstance(exc, HTTPError):
            return "MODEL_HTTP_ERROR: Ollama/model endpoint returned HTTP error."
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return "MODEL_TIMEOUT: Model request exceeded time limit."
        if isinstance(exc, URLError):
            return "MODEL_UNAVAILABLE: Cannot connect to model endpoint."
        if isinstance(exc, FileExistsError):
            return "PROJECT_EXISTS: Use another project slug."
        if isinstance(exc, ValueError):
            value = str(exc)
            if any(x in value for x in ("truncated", "incomplete", "complete HTML document",
                                         "incomplete code fence")):
                return "HTML_INCOMPLETE: Model output was not a complete document."
            if "Static quality gate FAIL" in value:
                return "HTML_QUALITY_FAILED: Static source rejected by quality gate."
            if any(x in value for x in ("too large", "exceeds", "byte limit")):
                return "HTML_TOO_LARGE: Generated HTML exceeded safe size limits."
            return "BUILDER_INVALID_OUTPUT: Generated website failed validation."
        return "BUILDER_EXECUTION_FAILED: Check model runtime and builder contracts."
    if skill_id.startswith("analytics."):
        from agentforge import analytics_insights as insights
        dataset, campaign = payload["dataset"], payload.get("campaign")
        if skill_id == "analytics.content_report":
            return insights.content_report(dataset, campaign=campaign)
        if skill_id == "analytics.trend_report":
            return insights.trend_report(dataset, campaign=campaign)
        if skill_id == "analytics.finance_report":
            return insights.finance_report(dataset, campaign=campaign)
        if skill_id == "analytics.quality_check":
            return insights.data_quality(dataset, campaign=campaign)
        if skill_id == "analytics.experiment_report":
            return insights.experiment_report(dataset, campaign)
        if skill_id == "analytics.opportunity_score":
            return insights.opportunity_report(dataset, campaign=campaign)
    if skill_id == "growth.campaign_create":
        from agentforge.growth_store import create_campaign
        return create_campaign(
            {key: value for key, value in payload.items() if key != "confirm_write"},
            confirm_write=True)
    if skill_id == "growth.bundle_prepare":
        from agentforge.growth_bundle import prepare
        return prepare(payload["campaign"], payload["channel"], payload["run_id"],
                       payload["title"], payload["description"],
                       confirm_rights=True, confirm_write=True)
    if skill_id == "growth.record_event":
        from agentforge.growth_store import record_event
        return record_event(payload["kind"], payload["data"], confirm_write=True)
    if skill_id.startswith("growth."):
        from agentforge import growth_reports
        campaign = payload["campaign"]
        if skill_id == "growth.report":
            return growth_reports.report(campaign)
        if skill_id == "growth.quality_check":
            return growth_reports.quality_check(campaign)
        if skill_id == "growth.reconcile":
            return growth_reports.reconcile(campaign)
    raise PermissionError("No trusted adapter")


def _safe_failure(skill_id, exc):
    """Stable, deliberately allowlisted errors; never serialize arbitrary exceptions."""
    if skill_id.startswith("analytics."):
        from agentforge.analytics_store import AnalyticsError
        if isinstance(exc, AnalyticsError):
            if str(exc) == "Dataset not found":
                return ("DATASET_NOT_FOUND: Dataset chưa được import. "
                        "Hãy chọn dataset có thật trong Intelligence.")
            if str(exc) == "No analytics dataset has been imported":
                return ("ANALYTICS_EMPTY: Chưa có dữ liệu Intelligence. "
                        "Hãy import dữ liệu được phép trước khi phân tích.")
    return f"{type(exc).__name__}: execution failed; inspect original module logs"


def _execute(task_id, skill_id, payload, *, grants, confirm_model_call,
             confirm_browser_run, confirm_external_run, db_path):
    missing = missing_grants(
        skill_id, grants, confirm_model_call=confirm_model_call,
        confirm_browser_run=confirm_browser_run,
        confirm_external_run=confirm_external_run, payload=payload)
    if missing:
        result = {"task_id": task_id, "skill_id": skill_id,
                  "status": "WAITING_APPROVAL", "missing": missing, "executed": False}
        if history.get_task(task_id, db_path=db_path)["status"] == "QUEUED":
            history.transition(task_id, "WAITING_APPROVAL", result=result, db_path=db_path)
        return result
    from agentforge.ops_control import require_active
    require_active()
    history.transition(task_id, "RUNNING", db_path=db_path)
    # Only permission NAMES/booleans enter audit, never tokens or payloads.
    _, required = _contract(skill_id)
    history.checkpoint(
        task_id, "POLICY_GRANTED",
        {"required": sorted(required),
         "model_confirmed": confirm_model_call is True,
         "browser_confirmed": confirm_browser_run is True,
         "external_confirmed": confirm_external_run is True},
        db_path=db_path,
    )
    try:
        result = _dispatch(skill_id, payload)
        registry.validate_payload(registry.load_skill(skill_id), result, direction="output")
        history.transition(task_id, "SUCCEEDED", result=result, db_path=db_path)
        return {"task_id": task_id, "skill_id": skill_id,
                "status": "SUCCEEDED", "executed": True, "result": result}
    except Exception as exc:
        # Do not serialize raw model text, URLs or secrets from exceptions.
        error = _safe_failure(skill_id, exc)
        history.transition(task_id, "FAILED", error=error, db_path=db_path)
        return {"task_id": task_id, "skill_id": skill_id,
                "status": "FAILED", "executed": True, "error": error}


def invoke(skill_id, payload, *, grants=(), confirm_model_call=False,
           confirm_browser_run=False, confirm_external_run=False,
           parent_id=None, db_path=None):
    skill, _ = _contract(skill_id)
    registry.validate_payload(skill, payload)
    # Reject nested S5 event fields (especially PII) before writing Task History.
    if skill_id == "growth.record_event":
        from agentforge.growth_store import validate_event_payload
        validate_event_payload(payload["kind"], payload["data"])
    # Reject malformed grants before recording a runnable task.
    missing_grants(skill_id, grants, confirm_model_call=confirm_model_call,
                   confirm_browser_run=confirm_browser_run,
                   confirm_external_run=confirm_external_run, payload=payload)
    from agentforge.ops_control import require_active
    require_active()
    task_id = history.create_task("skill", skill_id, payload,
                                  parent_id=parent_id, db_path=db_path)
    return _execute(task_id, skill_id, payload, grants=grants,
                    confirm_model_call=confirm_model_call,
                    confirm_browser_run=confirm_browser_run,
                    confirm_external_run=confirm_external_run, db_path=db_path)


def resume_waiting(task_id, *, grants=(), confirm_model_call=False,
                   confirm_browser_run=False, confirm_external_run=False,
                   db_path=None):
    from agentforge.ops_control import require_active
    require_active()
    task = history.get_task(task_id, db_path=db_path)
    if task["kind"] != "skill" or task["status"] != "WAITING_APPROVAL":
        raise ValueError("Only never-started approval tasks may be resumed")
    skill, _ = _contract(task["skill_id"])
    registry.validate_payload(skill, task["request"])
    if task["skill_id"] == "growth.record_event":
        from agentforge.growth_store import validate_event_payload
        validate_event_payload(task["request"]["kind"], task["request"]["data"])
    return _execute(task_id, task["skill_id"], task["request"], grants=grants,
                    confirm_model_call=confirm_model_call,
                    confirm_browser_run=confirm_browser_run,
                    confirm_external_run=confirm_external_run, db_path=db_path)


def main():
    parser = argparse.ArgumentParser(description="S1 owner-gated skill invocation")
    commands = parser.add_subparsers(dest="command", required=True)
    invoke_cmd = commands.add_parser("invoke")
    invoke_cmd.add_argument("skill_id")
    invoke_cmd.add_argument("--input-json")
    invoke_cmd.add_argument("--input-file")
    invoke_cmd.add_argument("--slug", help="Convenience for web quality/browser test")
    resume_cmd = commands.add_parser("resume")
    resume_cmd.add_argument("task_id")
    for cmd in (invoke_cmd, resume_cmd):
        cmd.add_argument("--grant", action="append", default=[])
        cmd.add_argument("--confirm-model-call", action="store_true")
        cmd.add_argument("--confirm-browser-run", action="store_true")
        cmd.add_argument("--confirm-external-run", action="store_true")
    args = parser.parse_args()
    if args.command == "resume":
        result = resume_waiting(args.task_id, grants=args.grant,
                                confirm_model_call=args.confirm_model_call,
                                confirm_browser_run=args.confirm_browser_run,
                                confirm_external_run=args.confirm_external_run)
    else:
        if sum(x is not None for x in (args.slug, args.input_json, args.input_file)) != 1:
            parser.error("Use exactly one of --slug, --input-json, --input-file")
        if args.slug is not None:
            if args.skill_id not in {"web.quality_check", "web.browser_test"}:
                parser.error("--slug is limited to web.quality_check/web.browser_test")
            payload = {"slug": args.slug}
            if args.skill_id == "web.browser_test":
                payload.update(confirm_browser_run=args.confirm_browser_run,
                               browser_channel="msedge")
        elif args.input_file is not None:
            path = Path(args.input_file)
            if path.stat().st_size > 8192:
                parser.error("JSON input too large")
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            payload = json.loads(args.input_json)
        result = invoke(args.skill_id, payload, grants=args.grant,
                        confirm_model_call=args.confirm_model_call,
                        confirm_browser_run=args.confirm_browser_run,
                        confirm_external_run=args.confirm_external_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] == "FAILED":
        parser.exit(2)
    if result["status"] == "WAITING_APPROVAL":
        parser.exit(3)


if __name__ == "__main__":
    main()
