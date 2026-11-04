"""C8F: bounded local Build -> Browser Test -> Fix Proposal workflow.

A session records immutable checkpoints in gitignored data/. One explicit
attempt per side-effecting step, no retries, no auto-apply and no deployment.
C8B owns all product writes; C8D and C8E own testing and fixing logic.
"""

import argparse
import json
from datetime import datetime, timezone
from uuid import uuid4

from agentforge import browser_fix
from agentforge import browser_validation as browser
from agentforge import product_builder as builder
from agentforge import product_revision as revision


EVENT_NAMES = frozenset({
    "start", "baseline_attempt", "baseline_result", "model_attempt",
    "model_result", "candidate_attempt", "candidate_result",
})
MAX_EVENT_BYTES = 12_000
MAX_REPORT_BYTES = browser_fix.MAX_REPORT_BYTES


def _folder(cycle_id):
    builder._check_proposal_id(cycle_id)
    path = (builder.ROOT / "data" / "company" / "product_builder"
            / "cycles" / cycle_id)
    builder._check_path_chain(path)
    return path


def _path(cycle_id, event):
    if event not in EVENT_NAMES:
        raise ValueError("Unknown cycle checkpoint type")
    path = _folder(cycle_id) / (event + ".json")
    builder._check_path_chain(path)
    return path


def _read_event(cycle_id, event, *, required=False):
    path = _path(cycle_id, event)
    if not path.is_file():
        if required:
            raise FileNotFoundError("Cycle checkpoint is missing: " + event)
        return None
    if not 0 < path.stat().st_size <= MAX_EVENT_BYTES:
        raise ValueError("Cycle checkpoint size invalid: " + event)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("Invalid cycle checkpoint: " + event)
    return doc


def _write_event(cycle_id, event, payload):
    path = _path(cycle_id, event)
    path.parent.mkdir(parents=True, exist_ok=True)
    builder._check_path_chain(path)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(payload, output, indent=2, ensure_ascii=False)
    return path


def _session(cycle_id):
    doc = _read_event(cycle_id, "start", required=True)
    if (set(doc) != {"schema_version", "cycle_id", "created_at", "project_slug",
                     "base_sha256", "attached_report", "limits",
                     "execution_authorized", "deployment_authorized"}
            or doc["schema_version"] != 1 or doc["cycle_id"] != cycle_id
            or not isinstance(doc["project_slug"], str)
            or builder._check_slug(doc["project_slug"]) != doc["project_slug"]
            or not isinstance(doc["base_sha256"], str)
            or not builder.SHA_RE.fullmatch(doc["base_sha256"])
            or doc["limits"] != {"browser_baseline": 1, "model": 1,
                                 "browser_candidate": 1}
            or doc["execution_authorized"] is not False
            or doc["deployment_authorized"] is not False):
        raise ValueError("Invalid C8F cycle start checkpoint")
    attached = doc["attached_report"]
    if attached is not None and (
            not isinstance(attached, dict)
            or set(attached) != {"run_id", "report_sha256", "status"}
            or not isinstance(attached["report_sha256"], str)
            or not builder.SHA_RE.fullmatch(attached["report_sha256"])):
        raise ValueError("Invalid attached report checkpoint")
    return doc


def _current(doc):
    _, raw, _ = revision._source(doc["project_slug"])
    if revision._hash(raw) != doc["base_sha256"]:
        raise RuntimeError("STALE_CYCLE: product changed since cycle began")
    return raw


def _snapshot_project(slug, run_id):
    data, _, _, path = browser_fix._read_report(run_id)
    if data["project_slug"] != slug:
        raise ValueError("C8D report belongs to a different project")
    contents = path.read_bytes()
    return {
        "run_id": run_id, "report_sha256": revision._hash(contents),
        "status": data["status"],
    }


def _snapshot_candidate(slug, revision_id, run_id):
    builder._check_proposal_id(run_id)
    doc, _, receipt = revision._read_revision(revision_id)
    if receipt.exists() or doc["project_slug"] != slug:
        raise RuntimeError("Pending C8B revision is missing or already applied")

    path = (builder.ROOT / "data" / "company" / "product_builder"
            / "browser_checks" / "revision" / revision_id / run_id / "report.json")
    builder._check_path_chain(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_REPORT_BYTES:
        raise ValueError("C8D candidate browser report missing or invalid")
    contents = path.read_bytes()
    report = json.loads(contents.decode("utf-8"))
    expected_sha = revision._hash(doc["files"][0]["content"].encode("utf-8"))
    if (not isinstance(report, dict)
            or report.get("schema_version") != 1
            or report.get("run_id") != run_id
            or report.get("target") != "revision"
            or report.get("identifier") != revision_id
            or report.get("project_slug") != slug
            or report.get("source_sha256") != expected_sha
            or report.get("browser_rendered") is not True
            or report.get("browser_run_approved") is not True
            or report.get("product_modified") is not False
            or report.get("deployment_authorized") is not False
            or report.get("status") not in {"PASS", "WARN", "FAIL"}
            or type(report.get("failures")) is not int
            or type(report.get("warnings")) is not int
            or report["failures"] < 0 or report["warnings"] < 0
            or not isinstance(report.get("viewports"), list)
            or len(report["viewports"]) != len(browser.VIEWPORTS)
            or not isinstance(report.get("findings"), list)):
        raise ValueError("Invalid C8D candidate browser report")
    if (report["status"] == "PASS" and (report["failures"] or report["warnings"])
            or report["status"] == "WARN" and (
                report["failures"] or not report["warnings"])
            or report["status"] == "FAIL" and not report["failures"]):
        raise ValueError("Inconsistent C8D candidate result")
    return {
        "run_id": run_id,
        "report_sha256": revision._hash(contents),
        "status": report["status"],
    }


def _baseline(doc, cycle_id):
    snapshot = doc["attached_report"]
    if snapshot is None:
        snapshot = _read_event(cycle_id, "baseline_result")
    if snapshot is None:
        return None
    current = _snapshot_project(doc["project_slug"], snapshot["run_id"])
    if (current["report_sha256"] != snapshot["report_sha256"]
            or current["status"] != snapshot["status"]):
        raise RuntimeError("CHANGED_REPORT: C8D baseline report changed after checkpoint")
    return current


def start(slug, *, report_run_id=None):
    """Start a cycle without browser/LLM; optionally reuse an existing C8D report."""
    slug = builder._check_slug(slug)
    _, raw, _ = revision._source(slug)
    attached = None
    if report_run_id is not None:
        attached = _snapshot_project(slug, report_run_id)
    cycle_id = uuid4().hex
    folder = _folder(cycle_id)
    folder.mkdir(parents=True, exist_ok=False)
    doc = {
        "schema_version": 1,
        "cycle_id": cycle_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_slug": slug,
        "base_sha256": revision._hash(raw),
        "attached_report": attached,
        "limits": {"browser_baseline": 1, "model": 1, "browser_candidate": 1},
        "execution_authorized": False,
        "deployment_authorized": False,
    }
    _write_event(cycle_id, "start", doc)
    return inspect(cycle_id)


def test(cycle_id, *, confirm_browser_run=False, browser_channel="bundled",
         browser_runner=None):
    """One explicit real-browser baseline attempt; never a background action."""
    doc = _session(cycle_id)
    _current(doc)
    if doc["attached_report"] is not None:
        raise RuntimeError("Cycle already has an attached C8D baseline report")
    if _read_event(cycle_id, "baseline_attempt") is not None:
        raise RuntimeError("Baseline browser was already attempted in this cycle")
    if confirm_browser_run is not True:
        raise PermissionError("Explicit --confirm-browser-run required")
    if browser_channel not in browser.BROWSER_CHANNELS:
        raise ValueError("Invalid installed browser channel")
    _write_event(cycle_id, "baseline_attempt",
                 {"browser_channel": browser_channel,
                  "created_at": datetime.now(timezone.utc).isoformat()})
    runner = browser_runner or browser.validate
    result = runner("project", doc["project_slug"],
                    confirm_browser_run=True, browser_channel=browser_channel)
    snapshot = _snapshot_project(doc["project_slug"], result["run_id"])
    if snapshot["status"] != result["status"]:
        raise RuntimeError("C8D report status mismatch")
    _write_event(cycle_id, "baseline_result", snapshot)
    return inspect(cycle_id)


def inspect(cycle_id):
    """Pure local checkpoint inspection; never calls AI or launches browser."""
    doc = _session(cycle_id)
    slug = doc["project_slug"]
    try:
        _current(doc)
    except (OSError, RuntimeError, ValueError):
        # Source may have been manually applied via C8B. Distinguish that from
        # other edits only if our exact generated revision is applied.
        result = _read_event(cycle_id, "model_result")
        if result is not None:
            proposal, _, receipt = revision._read_revision(result["revision_id"])
            if (receipt.exists() and proposal["project_slug"] == slug
                    and proposal["sha256"] == result["sha256"]):
                return {
                    "cycle_id": cycle_id, "project_slug": slug,
                    "status": "APPLIED_VIA_C8B",
                    "revision_id": result["revision_id"],
                    "automatic_apply": False,
                    "deployment_authorized": False,
                }
        return {"cycle_id": cycle_id, "project_slug": slug,
                "status": "STALE_CYCLE", "automatic_apply": False,
                "deployment_authorized": False}

    baseline = _baseline(doc, cycle_id)
    if baseline is None:
        status = ("BASELINE_ATTEMPT_INTERRUPTED"
                  if _read_event(cycle_id, "baseline_attempt")
                  else "AWAITING_BROWSER_TEST")
        return {"cycle_id": cycle_id, "project_slug": slug,
                "status": status, "automatic_apply": False,
                "deployment_authorized": False}

    plan = browser_fix.plan(baseline["run_id"])
    status = plan["status"]
    result = _read_event(cycle_id, "model_result")
    revision_id = result["revision_id"] if result else None
    candidate = None
    if result:
        proposal, _, receipt = revision._read_revision(revision_id)
        if proposal["sha256"] != result["sha256"]:
            raise ValueError("C8B revision proposal differs from C8F checkpoint")
        if receipt.exists():
            status = "APPLIED_VIA_C8B"
        else:
            candidate = _read_event(cycle_id, "candidate_result")
            if candidate:
                actual = _snapshot_candidate(slug, revision_id, candidate["run_id"])
                if actual != candidate:
                    raise RuntimeError("CHANGED_REPORT: C8D candidate report changed")
                status = {
                    "PASS": "READY_FOR_OWNER_REVIEW",
                    "WARN": "CANDIDATE_WARN_REVIEW_REQUIRED",
                    "FAIL": "CANDIDATE_FAILED",
                }[actual["status"]]
            elif _read_event(cycle_id, "candidate_attempt") is not None:
                status = "CANDIDATE_ATTEMPT_INTERRUPTED"
            else:
                status = "AWAITING_CANDIDATE_BROWSER_TEST"
    elif _read_event(cycle_id, "model_attempt") is not None:
        status = "MODEL_ATTEMPT_INTERRUPTED"
    return {
        "cycle_id": cycle_id,
        "project_slug": slug,
        "status": status,
        "baseline_run_id": baseline["run_id"],
        "baseline_status": baseline["status"],
        "revision_id": revision_id,
        "candidate_run_id": candidate["run_id"] if candidate else None,
        "automatic_apply": False,
        "model_calls_budget": 1,
        "deployment_authorized": False,
    }


def propose(cycle_id, *, confirm_model_call=False, model_client=None):
    """One explicitly approved model attempt, only if C8E found fixable issues."""
    doc = _session(cycle_id)
    _current(doc)
    baseline = _baseline(doc, cycle_id)
    if baseline is None:
        raise RuntimeError("C8D baseline report required before proposing fixes")
    plan = browser_fix.plan(baseline["run_id"])
    if plan["status"] != "FIX_PROPOSAL_AVAILABLE":
        return inspect(cycle_id)
    if _read_event(cycle_id, "model_attempt") is not None:
        raise RuntimeError("Model already attempted in this cycle; no retry")
    if confirm_model_call is not True:
        raise PermissionError("Explicit --confirm-model-call required")
    _write_event(cycle_id, "model_attempt", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_run_id": baseline["run_id"],
        "approved_by_owner": True,
    })
    result = browser_fix.propose(
        baseline["run_id"],
        confirm_model_call=True,
        model_client=model_client,
    )
    if result["status"] != "PROPOSED_NOT_APPLIED":
        raise RuntimeError("C8E did not return a pending revision")
    _write_event(cycle_id, "model_result", {
        "revision_id": result["revision_id"], "sha256": result["sha256"],
    })
    return inspect(cycle_id)


def test_revision(cycle_id, *, confirm_browser_run=False,
                  browser_channel="bundled", browser_runner=None):
    """One explicit browser check on a proposed, not-yet-applied C8B revision."""
    doc = _session(cycle_id)
    _current(doc)
    _baseline(doc, cycle_id)
    result = _read_event(cycle_id, "model_result", required=True)
    revision_id = result["revision_id"]
    proposal, _, receipt = revision._read_revision(revision_id)
    if receipt.exists():
        raise RuntimeError("Revision already applied; check project instead")
    if proposal["project_slug"] != doc["project_slug"] or proposal["sha256"] != result["sha256"]:
        raise RuntimeError("C8B proposal does not match cycle")
    revision._require_current(proposal)
    if _read_event(cycle_id, "candidate_attempt") is not None:
        raise RuntimeError("Candidate browser was already attempted in this cycle")
    if confirm_browser_run is not True:
        raise PermissionError("Explicit --confirm-browser-run required")
    if browser_channel not in browser.BROWSER_CHANNELS:
        raise ValueError("Invalid installed browser channel")
    _write_event(cycle_id, "candidate_attempt", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "browser_channel": browser_channel,
        "revision_id": revision_id,
    })
    runner = browser_runner or browser.validate
    result = runner("revision", revision_id, confirm_browser_run=True,
                    browser_channel=browser_channel)
    snapshot = _snapshot_candidate(doc["project_slug"], revision_id,
                                   result["run_id"])
    if result["status"] != snapshot["status"]:
        raise RuntimeError("C8D candidate result does not match its report")
    _write_event(cycle_id, "candidate_result", snapshot)
    return inspect(cycle_id)


def main():
    parser = argparse.ArgumentParser(
        description="C8F bounded, owner-controlled browser feedback cycle")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start", help="Track an existing product without running AI/browser")
    p.add_argument("slug")
    p.add_argument("--report-run-id", help="Reuse existing C8D project report")
    p = sub.add_parser("inspect", help="Read local cycle status, no external actions")
    p.add_argument("cycle_id")
    p = sub.add_parser("test", help="Run baseline browser once with explicit permission")
    p.add_argument("cycle_id")
    p.add_argument("--confirm-browser-run", action="store_true")
    p.add_argument("--browser-channel", choices=browser.BROWSER_CHANNELS,
                   default="bundled")
    p = sub.add_parser("propose", help="One paid-model attempt if C8D found issues")
    p.add_argument("cycle_id")
    p.add_argument("--confirm-model-call", action="store_true")
    p = sub.add_parser("test-revision", help="Check pending C8B revision in browser once")
    p.add_argument("cycle_id")
    p.add_argument("--confirm-browser-run", action="store_true")
    p.add_argument("--browser-channel", choices=browser.BROWSER_CHANNELS,
                   default="bundled")
    args = parser.parse_args()
    if args.command == "start":
        result = start(args.slug, report_run_id=args.report_run_id)
    elif args.command == "inspect":
        result = inspect(args.cycle_id)
    elif args.command == "test":
        result = test(args.cycle_id,
                      confirm_browser_run=args.confirm_browser_run,
                      browser_channel=args.browser_channel)
    elif args.command == "propose":
        result = propose(args.cycle_id,
                         confirm_model_call=args.confirm_model_call)
    else:
        result = test_revision(args.cycle_id,
                               confirm_browser_run=args.confirm_browser_run,
                               browser_channel=args.browser_channel)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
