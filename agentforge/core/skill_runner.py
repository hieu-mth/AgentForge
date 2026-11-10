"""S1 allowlisted skill adapters; explicit per-call grants and durable results.

This is a local owner CLI, not OS isolation or multi-user authentication.
"""
import argparse
import json
from pathlib import Path

from agentforge import skill_registry as registry
from agentforge import task_history as history
from agentforge.core.skill_adapters import POLICY, dispatch as _dispatch

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


def _safe_failure(skill_id, exc):
    """Stable, deliberately allowlisted errors; never serialize arbitrary exceptions."""
    from agentforge.domains.webapps.syntax import SourceSyntaxError
    if isinstance(exc, SourceSyntaxError):
        # Typed parser diagnostics only; never expose generated source snippets.
        return str(exc)
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
        if isinstance(exc, json.JSONDecodeError):
            return "MODEL_JSON_INVALID: AI did not produce valid structured JSON."
        if isinstance(exc, ValueError):
            value = str(exc)
            if value.startswith("REVISION_NO_CHANGE:"):
                return ("WEBSITE_UNCHANGED: AI returned the same website. "
                        "No new proposal was saved; specify a concrete change.")
            if value.startswith("Structured website content invalid:"):
                return ("WEB_COPY_INVALID: AI content failed the bounded website "
                        "copy contract; no proposal saved.")
            if value == "Invalid owner phone number":
                return "OWNER_CONTACT_INVALID: The supplied phone format is not supported."
            if any(x in value for x in ("truncated", "incomplete", "complete HTML document",
                                         "incomplete code fence")):
                return "HTML_INCOMPLETE: Model output was not a complete document."
            if "Static quality gate FAIL" in value:
                return "HTML_QUALITY_FAILED: Static source rejected by quality gate."
            if any(x in value for x in ("too large", "exceeds", "byte limit")):
                return "HTML_TOO_LARGE: Generated HTML exceeded safe size limits."
            # Classify known builder contract failures without persisting raw
            # model output, exception bodies, filesystem paths or credentials.
            if "Disallowed active/remote content" in value:
                # Classify only our trusted builder error labels. Never expose
                # the rejected HTML, raw URL, or exception text to the UI.
                if "remote URL at line" in value:
                    return ("HTML_REMOTE_URL: Website draft contains a blocked "
                            "external URL. Use offline SVG/CSS instead of online assets.")
                if "active/embedded content at line" in value:
                    return ("HTML_ACTIVE_CONTENT: Website draft contains a "
                            "blocked embedded element or browser API.")
                return "HTML_UNSAFE_CONTENT: External resources or active content blocked."
            if "script source" in value:
                return "HTML_SCRIPT_SOURCE: Only a local app.js script is allowed."
            if any(marker in value for marker in (
                "unexpected object", "Expected 1-4 product files",
                "Invalid product file", "duplicate product filename",
                "requires index.html", "Product file cannot be empty",
                "Builder must return HTML text",
            )):
                return "BUILDER_SCHEMA_INVALID: Model output did not match the file contract."
            if any(marker in value for marker in (
                "must start with", "incomplete code fence",
                "incomplete", "truncated",
            )):
                return "HTML_INCOMPLETE: Model output was not a complete document."
            return "BUILDER_INVALID_OUTPUT: Generated website failed validation."
        return "BUILDER_EXECUTION_FAILED: Check model runtime and builder contracts."
    if skill_id in {"webapp.architect", "webapp.audit", "webapp.review"}:
        import socket
        from urllib.error import HTTPError, URLError
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return "V5_MODEL_TIMEOUT: Check chosen model and approved budget."
        if isinstance(exc, (HTTPError, URLError)):
            return "V5_MODEL_UNAVAILABLE: Configured model endpoint failed."
        if isinstance(exc, PermissionError):
            return "V5_SOURCE_OR_MODEL_DENIED: Source SHA or cloud consent required."
        if isinstance(exc, json.JSONDecodeError):
            return "V5_MODEL_JSON_INVALID: Model response or signed document is not valid JSON."
        if isinstance(exc, ValueError):
            # Only recognize fixed validator labels from trusted V5 modules.
            # Never include arbitrary exception bodies or model-generated text.
            label = str(exc)
            if skill_id == "webapp.architect" and label.startswith("ARCHITECTURE_INVALID:"):
                # Field names are fixed by the reviewed contract, not echoed
                # from the model. This identifies the rejection without leaking text.
                field = label.removeprefix("ARCHITECTURE_INVALID:").strip()
                if field in {"title", "audience", "purpose", "ui_sections",
                             "user_flows", "local_data", "constraints"}:
                    return ("V5_ARCHITECTURE_SCHEMA_INVALID: Invalid Architect "
                            + field + " field (type, count, or length).")
                return "V5_ARCHITECTURE_SCHEMA_INVALID: Architect output does not meet the required schema."
            if skill_id == "webapp.review" and label.startswith("REVIEW_INVALID:"):
                field = label.removeprefix("REVIEW_INVALID:").strip()
                if field in {"recommendation", "summary", "missing_features", "risks"}:
                    return ("V5_REVIEW_SCHEMA_INVALID: Invalid Reviewer "
                            + field + " field (type, count, or length).")
                return "V5_REVIEW_SCHEMA_INVALID: Reviewer output does not meet the required schema."
            if skill_id == "webapp.review" and label.startswith("ARCHITECTURE_INVALID:"):
                return "V5_ARCHITECTURE_SOURCE_INVALID: Signed architecture failed validation."
            if skill_id == "webapp.review" and label.startswith("APP_CODE_"):
                return "V5_APP_SOURCE_INVALID: Reviewed React proposal failed validation."
            return "V5_OUTPUT_INVALID: Signed source or model schema validation failed."
        return "V5_STAGE_FAILED: No code executed or deployed."
    if skill_id == "webapp.develop":
        import socket
        from urllib.error import HTTPError, URLError
        from agentforge.model_registry import ModelConfigError
        from agentforge.worker_registry import WorkerConfigError
        if isinstance(exc, HTTPError):
            if getattr(exc, "code", None) == 429:
                return "MODEL_RATE_LIMITED: Model provider rate limit; no automatic retry."
            return "MODEL_HTTP_ERROR: AI Developer model endpoint rejected the request."
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return ("MODEL_TIMEOUT: AI Developer response timed out. "
                    "Try a smaller scope or configure AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS.")
        if isinstance(exc, URLError):
            if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
                return ("MODEL_TIMEOUT: AI Developer response timed out. "
                        "Try a smaller scope or configure AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS.")
            return "MODEL_UNAVAILABLE: Cannot reach the configured model."
        if isinstance(exc, PermissionError):
            return "MODEL_PERMISSION_DENIED: Check cloud consent and source SHA permissions."
        if isinstance(exc, (ModelConfigError, WorkerConfigError)):
            return "MODEL_CONFIG_INVALID: Check worker model and provider configuration."
        if isinstance(exc, FileExistsError):
            return "APP_PROJECT_EXISTS: Use a new project slug."
        if isinstance(exc, json.JSONDecodeError):
            return "APP_CODE_JSON_INVALID: Model returned incomplete or invalid JSON."
        if isinstance(exc, ValueError):
            if str(exc).startswith("APP_CODE_METADATA_INVALID:"):
                field = str(exc).split(":", 1)[1].strip()
                if field == "title":
                    return "APP_CODE_TITLE_INVALID: AI returned an empty or invalid React title."
                if field == "summary":
                    return "APP_CODE_SUMMARY_INVALID: AI returned an empty or invalid React summary."
                return "APP_CODE_METADATA_INVALID: AI returned invalid display metadata."
            if str(exc).startswith("APP_CODE_UNSAFE:"):
                # Only trusted, fixed categories may reach task history. Never
                # echo matched source text, file paths or exception contents.
                code = str(exc).split(":", 1)[1].strip()
                guidance = {
                    "REMOTE_URL": "Remote URL in generated React. Use local CSS or SVG shapes.",
                    "ACTIVE_API": "Blocked browser or runtime API. Use local React state only.",
                    "DYNAMIC_IMPORT": "Dynamic import or code execution is not permitted.",
                    "EMBEDDED_HTML": "Blocked embedded HTML tag; use safe React components.",
                    "CSS_ASSET": "CSS imports, url() and active expressions are disallowed.",
                    "CSS_MARKUP": "HTML markup inside CSS is disallowed.",
                    "EXTERNAL_PACKAGE": "Only React and allowlisted local imports are permitted.",
                    "UNAPPROVED_MODULE": "Import does not resolve to an allowlisted local module.",
                }
                return ("APP_CODE_UNSAFE: " + guidance.get(
                    code, "Generated code includes blocked remote/active patterns."))
            if str(exc).startswith("APP_REVISION_UNCHANGED:"):
                return ("APP_REVISION_UNCHANGED: AI did not edit source code. "
                        "Please request specific file/UI changes; no proposal saved.")
            if str(exc).startswith("APP_REVISION_INVALID:"):
                return ("APP_REVISION_INVALID: Code edit failed the bounded patch contract; "
                        "original source was preserved.")
            if str(exc).startswith("APP_CODE_INVALID:"):
                return "APP_CODE_INVALID: Generated React source failed the file contract."
            if str(exc).startswith("APP_ARCHITECTURE_"):
                return "APP_ARCHITECTURE_INVALID: Signed Architect input is invalid."
            return "APP_CODE_CONTRACT_INVALID: Generated React metadata/fields failed validation."
        if isinstance(exc, RuntimeError):
            reason = str(exc)
            # Match only fixed errors originating from our trusted model adapter,
            # never copy the exception body or model output to task history.
            if reason.startswith("Gateway response stopped at max_tokens"):
                return ("MODEL_OUTPUT_LIMIT: React JSON exceeded the cloud response "
                        "token budget. Try a smaller app scope or a capable model.")
            if (reason.startswith("Gateway returned no text content")
                    or reason.startswith("Gateway response has no content blocks")
                    or reason.startswith("Ollama returned an empty answer")):
                return "MODEL_EMPTY_OUTPUT: Model returned no usable text."
            if reason.startswith("Model did not return a JSON object"):
                return "MODEL_JSON_OBJECT_REQUIRED: Model returned a non-object JSON value."
            if reason.startswith("Ollama stream ended before done"):
                return "MODEL_STREAM_INCOMPLETE: Local model stopped before completing React JSON."
            if reason.startswith("Ollama stream exceeds safe size limit"):
                return "MODEL_STREAM_TOO_LARGE: Local model exceeded the response safety limit."
            return "MODEL_RUNTIME_FAILED: Model gateway or generation failed."
        if isinstance(exc, OSError):
            return "APP_LOCAL_IO_FAILED: Cannot read the local template or write proposal."
        return "APP_CODE_INTERNAL: Unexpected builder exception; no code was executed."
    if skill_id in {"webapp.sandbox_test", "webapp.browser_qa"}:
        label = str(exc)
        if isinstance(exc, ValueError) and label.startswith("TOOLCHAIN_STALE"):
            return "TOOLCHAIN_STALE: Create a new proposal using the patched locked scaffold."
        if isinstance(exc, (RuntimeError, PermissionError)) and label.startswith(
                "SANDBOX_UNAVAILABLE"):
            return "SANDBOX_UNAVAILABLE: Configure Docker and a pinned local Linux QA image."
        if isinstance(exc, RuntimeError) and label.startswith("SANDBOX_TIMEOUT"):
            return "SANDBOX_TIMEOUT: Container build/test exceeded its time limit."
        if isinstance(exc, RuntimeError) and label.startswith("BROWSER_QA_RUNTIME_FAILED"):
            return "BROWSER_QA_RUNTIME_FAILED: Trusted offline browser process failed."
        if isinstance(exc, ValueError) and label.startswith("BROWSER_QA_"):
            return "BROWSER_QA_INVALID_RESULT: Browser evidence did not pass validation."
        if isinstance(exc, RuntimeError) and label.startswith("SANDBOX_BUILD_FAILED"):
            return "SANDBOX_BUILD_FAILED: React tests/build did not pass in the container."
        if isinstance(exc, PermissionError) and label.startswith("SANDBOX_SOURCE_STALE"):
            return "SANDBOX_SOURCE_STALE: Proposal SHA no longer matches."
        return "SANDBOX_FAILED: Review local Docker setup; no native code executed."
    if skill_id == "webapp.create":
        import socket
        from urllib.error import HTTPError, URLError
        if isinstance(exc, HTTPError):
            return "MODEL_HTTP_ERROR: Marketplace AI model returned an HTTP error."
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return "MODEL_TIMEOUT: Marketplace AI call timed out."
        if isinstance(exc, URLError):
            return "MODEL_UNAVAILABLE: Cannot reach model endpoint."
        if isinstance(exc, json.JSONDecodeError):
            return "MODEL_JSON_INVALID: AI output was not valid JSON."
        if isinstance(exc, FileExistsError):
            return "APP_PROJECT_EXISTS: Choose a different app project name."
        if isinstance(exc, ValueError) and str(exc).startswith("APP_SPEC_INVALID:"):
            return "APP_SPEC_INVALID: AI data was not valid marketplace demo data."
        if isinstance(exc, ValueError) and str(exc).startswith("APP_TOO_LARGE"):
            return "APP_TOO_LARGE: Application proposal exceeded safe limits."
        if isinstance(exc, ValueError) and str(exc).startswith("APP_REVISION_UNCHANGED:"):
            return "APP_REVISION_UNCHANGED: AI returned no visible changes; original retained."
        if isinstance(exc, PermissionError) and str(exc).startswith("APP_SOURCE_STALE:"):
            return "APP_SOURCE_STALE: Reviewed application proposal changed."
        if isinstance(exc, ValueError) and str(exc).startswith("APP_REVISION_INVALID:"):
            return "APP_REVISION_INVALID: Source or change request did not pass validation."
        return "WEBAPP_BUILD_FAILED: No app was executed or published."
    if skill_id == "media.copy_draft":
        import socket
        from urllib.error import HTTPError, URLError
        from agentforge.model_registry import ModelConfigError
        from agentforge.worker_registry import WorkerConfigError
        if isinstance(exc, HTTPError):
            return "STORYBOARD_MODEL_HTTP_ERROR: Model provider rejected this request."
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return "STORYBOARD_MODEL_TIMEOUT: Model did not respond in time."
        if isinstance(exc, URLError):
            return "STORYBOARD_MODEL_UNAVAILABLE: Cannot reach configured model."
        if isinstance(exc, (ModelConfigError, WorkerConfigError)):
            return "STORYBOARD_MODEL_CONFIG_INVALID: Check media model/worker route."
        if isinstance(exc, PermissionError):
            return "STORYBOARD_PERMISSION_DENIED: Check model authorization."
        if isinstance(exc, json.JSONDecodeError):
            return "STORYBOARD_MODEL_JSON_INVALID: Model did not return valid JSON."
        if isinstance(exc, ValueError):
            label = str(exc)
            if label.startswith("STORYBOARD_INPUT_INVALID:"):
                field = label.removeprefix("STORYBOARD_INPUT_INVALID:").strip()
                if field in {"topic", "audience", "goal"}:
                    return "STORYBOARD_INPUT_INVALID: Invalid " + field + " (type or length)."
            if label.startswith("STORYBOARD_SCHEMA_INVALID:"):
                field = label.removeprefix("STORYBOARD_SCHEMA_INVALID:").strip()
                if field in {"fields", "title", "scenes"}:
                    return "STORYBOARD_SCHEMA_INVALID: Invalid " + field + " in model output."
            return "STORYBOARD_VALIDATION_FAILED: Draft did not satisfy media constraints."
        if isinstance(exc, RuntimeError):
            label = str(exc)
            if label.startswith("Gateway response stopped at max_tokens"):
                return "STORYBOARD_OUTPUT_LIMIT: Model hit output token budget; no partial draft saved."
            if (label.startswith("Gateway returned no text content")
                    or label.startswith("Gateway response has no content blocks")
                    or label.startswith("Ollama returned an empty answer")):
                return "STORYBOARD_MODEL_EMPTY: Model returned no usable text."
            return "STORYBOARD_MODEL_RUNTIME_FAILED: Gateway or generation failed."
        if isinstance(exc, OSError):
            return "STORYBOARD_LOCAL_IO_FAILED: Local media data could not be read."
        return "STORYBOARD_INTERNAL_FAILED: No video was rendered."
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
        from agentforge.core import artifact_acceptance
        try:
            artifact_acceptance.observe(skill_id, result, db_path=db_path)
        except FileNotFoundError:
            # Execution receipts and artifact verification are separate contracts.
            # A missing legacy/injected artifact never manufactures acceptance.
            history.checkpoint(task_id, "ARTIFACT_SOURCE_MISSING", {"verified": False}, db_path=db_path)
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
