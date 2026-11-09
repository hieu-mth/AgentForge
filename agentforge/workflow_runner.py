"""S1 bounded website audit: quality -> optional consented browser check.

Checkpoints survive restarts. A pending browser step may be resumed after
explicit approval; completed or interrupted actions are NEVER replayed.
"""
import argparse
import json

from agentforge import product_builder, product_quality, skill_runner, task_history

WORKFLOW_ID = "workflow.web_audit"


def _receipt(task_id, state, quality=None, browser=None, missing=None):
    result = {"task_id": task_id, "workflow": WORKFLOW_ID, "status": state}
    if quality is not None:
        result["quality"] = quality
    if browser is not None:
        result["browser"] = browser
    if missing:
        result["missing"] = missing
    return result


def run_web_audit(slug=None, *, include_browser=False, grants=(),
                  confirm_browser_run=False, task_id=None, db_path=None):
    """Run once or continue a waiting browser step with a source-SHA check."""
    if task_id is None:
        slug = product_builder._check_slug(slug)
        task_id = task_history.create_task(
            "workflow", WORKFLOW_ID,
            {"slug": slug, "include_browser": bool(include_browser)}, db_path=db_path)
        stored = None
    else:
        previous = task_history.get_task(task_id, db_path=db_path)
        if (previous["kind"] != "workflow" or previous["skill_id"] != WORKFLOW_ID
                or previous["status"] != "WAITING_APPROVAL"):
            raise ValueError("Only a waiting web.audit task can be resumed")
        slug = product_builder._check_slug(previous["request"]["slug"])
        include_browser = previous["request"]["include_browser"]
        stored = previous["result"]
        if not include_browser or not isinstance(stored, dict) or "quality" not in stored:
            raise ValueError("Invalid web.audit checkpoint")
        if stored["quality"]["result"]["sha256"] != product_quality.check_project(slug)["sha256"]:
            task_history.transition(task_id, "FAILED",
                                    error="Website source changed after quality checkpoint",
                                    db_path=db_path)
            return _receipt(task_id, "FAILED")

    task_history.transition(task_id, "RUNNING", db_path=db_path)
    try:
        if stored is None:
            quality = skill_runner.invoke("web.quality_check", {"slug": slug},
                                          parent_id=task_id, db_path=db_path)
            if quality["status"] != "SUCCEEDED":
                result = _receipt(task_id, "FAILED", quality=quality)
                task_history.transition(task_id, "FAILED", result=result,
                                        error="Static quality adapter failed", db_path=db_path)
                return result
            task_history.checkpoint(
                task_id, "QUALITY_DONE",
                {"child_task_id": quality["task_id"],
                 "source_sha256": quality["result"]["sha256"]}, db_path=db_path)
        else:
            quality = stored["quality"]

        if quality["result"]["status"] == "FAIL":
            result = _receipt(task_id, "FAILED", quality=quality)
            task_history.transition(task_id, "FAILED", result=result,
                                    error="Static quality reported FAIL", db_path=db_path)
            return result

        if not include_browser:
            result = _receipt(task_id, "SUCCEEDED", quality=quality)
            task_history.transition(task_id, "SUCCEEDED", result=result, db_path=db_path)
            return result

        payload = {"slug": slug, "confirm_browser_run": confirm_browser_run,
                   "browser_channel": "msedge"}
        missing = skill_runner.missing_grants(
            "web.browser_test", grants, confirm_browser_run=confirm_browser_run,
            payload=payload)
        if missing:
            result = _receipt(task_id, "WAITING_APPROVAL", quality=quality, missing=missing)
            task_history.transition(task_id, "WAITING_APPROVAL", result=result, db_path=db_path)
            return result

        # Source may have changed while waiting for approval or after quality.
        if product_quality.check_project(slug)["sha256"] != quality["result"]["sha256"]:
            result = _receipt(task_id, "FAILED", quality=quality)
            task_history.transition(task_id, "FAILED", result=result,
                                    error="Source changed before browser run", db_path=db_path)
            return result

        browser = skill_runner.invoke(
            "web.browser_test", payload, grants=grants,
            confirm_browser_run=True, parent_id=task_id, db_path=db_path)
        task_history.checkpoint(task_id, "BROWSER_DONE",
                                {"child_task_id": browser["task_id"],
                                 "state": browser["status"]}, db_path=db_path)
        state = ("SUCCEEDED" if browser["status"] == "SUCCEEDED"
                 and browser["result"]["status"] != "FAIL" else "FAILED")
        result = _receipt(task_id, state, quality=quality, browser=browser)
        task_history.transition(task_id, state, result=result,
                                error="Browser validation failed" if state == "FAILED" else None,
                                db_path=db_path)
        return result
    except Exception as exc:
        task_history.transition(task_id, "FAILED",
                                error=f"{type(exc).__name__}: workflow failed",
                                db_path=db_path)
        return _receipt(task_id, "FAILED")


def main():
    parser = argparse.ArgumentParser(description="S1 bounded local web audit workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("slug")
    run.add_argument("--browser", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("task_id")
    for action in (run, resume):
        action.add_argument("--grant", action="append", default=[])
        action.add_argument("--confirm-browser-run", action="store_true")
    args = parser.parse_args()
    if args.command == "run":
        result = run_web_audit(args.slug, include_browser=args.browser,
                               grants=args.grant,
                               confirm_browser_run=args.confirm_browser_run)
    else:
        result = run_web_audit(task_id=args.task_id, grants=args.grant,
                               confirm_browser_run=args.confirm_browser_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] == "FAILED":
        parser.exit(2)
    if result["status"] == "WAITING_APPROVAL":
        parser.exit(3)


if __name__ == "__main__":
    main()
