"""V1.5 owner-edited storyboard -> local assets -> consented MP4 -> QA -> owner decision.

No model calls, publication, networking, credential use, or automatic retry.
Uses the existing S1 skill permission gates and S2 immutable artifacts.
"""
import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge import brain_store, media_assets, media_quality, ops_control
from agentforge import quality_v14, skill_runner

DB = brain_store.ROOT / "data" / "company" / "media_workflow_v15.sqlite3"
MAX_INPUT = 8192
STATES = {"PREPARING", "ASSETS_READY", "RENDERING", "VIDEO_READY",
          "QA_FAILED", "APPROVED", "REJECTED"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(obj):
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _db(path=None, *, create=False):
    target = Path(path) if path is not None else DB
    brain_store._safe(target)
    if not create and not target.is_file():
        return None
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
        brain_store._safe(target.parent)
    db = sqlite3.connect(target, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=20000")
    if create:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS productions (
          production_id TEXT PRIMARY KEY, storyboard_sha TEXT NOT NULL,
          source_job_id TEXT, source_output_sha TEXT, context_sha TEXT,
          run_id TEXT UNIQUE, task_id TEXT, render_task_id TEXT,
          video_sha TEXT, status TEXT NOT NULL,
          quality TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, error_code TEXT);
        """)
    return db


def _storyboard(data):
    if not isinstance(data, dict) or set(data) != {"slug", "title", "scenes"}:
        raise ValueError("Owner storyboard must have exactly slug/title/scenes")
    return {"slug": media_assets._slug(data["slug"]),
            "title": media_assets._text(data["title"], "title", 88),
            "scenes": media_assets._scenes(data["scenes"])}


def _business_check(data, *, autopilot_db_path=None):
    from agentforge.autopilot_v13 import _connect
    with closing(_connect(autopilot_db_path, create=True)) as db:
        profile = quality_v14.current_profile(db)
        if profile is None:
            raise PermissionError("V1.4 owner business context is required")
        candidate = {"title": data["title"], "scenes": data["scenes"],
                     "verified_claims": False, "review_required": True}
        check = quality_v14.assess("media.copy_draft", candidate, profile)
        if check["quality"] != "PASS_HEURISTIC":
            raise PermissionError("Edited storyboard failed business context check")
        return quality_v14._sha(profile)


def _verify_storyboard_manifest(record):
    folder, manifest = media_assets.load_manifest(record["run_id"])
    snapshot = _storyboard({
        "slug": manifest["slug"], "title": manifest["title"],
        "scenes": manifest["scenes"],
    })
    if _digest(snapshot) != record["storyboard_sha"]:
        raise PermissionError("Media storyboard changed since owner edit")
    return folder, manifest


def _link_source(source_job_id, source_output_sha, *, autopilot_db_path=None):
    if source_job_id is None and source_output_sha is None:
        return None, None
    if source_job_id is None or source_output_sha is None:
        raise ValueError("Both source job ID and review output SHA required")
    brain_store._id(source_job_id)
    if not isinstance(source_output_sha, str) or not brain_store.SHA.fullmatch(source_output_sha):
        raise ValueError("Invalid source output SHA")
    from agentforge.autopilot_v13 import _connect
    with closing(_connect(autopilot_db_path, create=True)) as db:
        row = db.execute("""SELECT decision,output_sha,skill_id FROM content_reviews
                            WHERE job_id=?""", (source_job_id,)).fetchone()
        if (row is None or row["output_sha"] != source_output_sha
                or row["skill_id"] != "media.copy_draft"
                or row["decision"] not in ("REJECTED", "APPROVED")):
            raise PermissionError("Source must be an owner-reviewed storyboard with matching SHA")
    return source_job_id, source_output_sha


def _row(production_id, *, db_path=None):
    brain_store._id(production_id)
    db = _db(db_path)
    if db is None:
        raise KeyError("Production not found")
    with closing(db):
        found = db.execute("SELECT * FROM productions WHERE production_id=?",
                           (production_id,)).fetchone()
        if found is None:
            raise KeyError("Production not found")
        return dict(found)


def prepare(storyboard, *, confirm_edit=False, visual_plan=None, source_job_id=None,
            source_output_sha=None, db_path=None, autopilot_db_path=None):
    """One owner-approved source edit. Never silently copies rejected model output."""
    if confirm_edit is not True:
        raise PermissionError("Explicit owner approval of edited storyboard required")
    ops_control.require_active()
    data = _storyboard(storyboard)
    visuals = media_assets.validate_visual_plan(visual_plan, len(data["scenes"]))
    context_sha = _business_check(data, autopilot_db_path=autopilot_db_path)
    source_job_id, source_output_sha = _link_source(
        source_job_id, source_output_sha, autopilot_db_path=autopilot_db_path)
    production_id, now = uuid4().hex, _now()
    with closing(_db(db_path, create=True)) as db:
        with db:
            db.execute("INSERT INTO productions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (production_id, _digest(data), source_job_id, source_output_sha,
                        context_sha, None, None, None, None, "PREPARING",
                        None, now, now, None))
    # The permanent PREPARING marker is intentionally not retried automatically.
    try:
        receipt = skill_runner.invoke("media.compose", {
            **data, "visual_plan": visuals},
                                      grants=("workspace.write",))
        if receipt["status"] != "SUCCEEDED":
            raise RuntimeError("Media compose did not succeed")
        run_id = receipt["result"]["run_id"]
        report = media_quality.check(run_id)
        if report["status"] != "ASSETS_PASS" or report["failures"]:
            raise RuntimeError("Prepared media assets failed quality check")
        with closing(_db(db_path, create=True)) as db:
            with db:
                updated = db.execute("""UPDATE productions SET
                    run_id=?,task_id=?,status='ASSETS_READY',quality=?,
                    updated_at=? WHERE production_id=? AND status='PREPARING'""",
                    (run_id, receipt["task_id"], "ASSETS_PASS", _now(), production_id))
                if updated.rowcount != 1:
                    raise RuntimeError("Production changed during prepare")
        return {"production_id": production_id, "status": "ASSETS_READY",
                "run_id": run_id, "storyboard_sha": _digest(data),
                "source_job_id": source_job_id, "model_calls": 0,
                "requires_owner_video_review": True,
                "visual_mode": visuals["mode"], "motion": visuals["motion"]}
    except Exception:
        # No replay: local assets may exist after power loss.
        raise


def render(production_id, *, confirm_local_process=False, db_path=None):
    """Explicit owner-gated local FFmpeg invocation; never retries uncertain renders."""
    if confirm_local_process is not True:
        raise PermissionError("Owner consent for local FFmpeg subprocess required")
    ops_control.require_active()
    record = _row(production_id, db_path=db_path)
    if record["status"] != "ASSETS_READY":
        raise PermissionError("Only prepared production can render once")
    _verify_storyboard_manifest(record)
    with closing(_db(db_path, create=True)) as db:
        with db:
            changed = db.execute("""UPDATE productions SET status='RENDERING',updated_at=?
                 WHERE production_id=? AND status='ASSETS_READY'""",
                 (_now(), production_id))
            if changed.rowcount != 1:
                raise PermissionError("Production already claimed for rendering")
    try:
        run_id = record["run_id"]
        receipt = skill_runner.invoke(
            "media.video_render", {"run_id": run_id, "confirm_external_run": True},
            grants=("workspace.write", "process.run"),
            confirm_external_run=True)
        if receipt["status"] != "SUCCEEDED":
            raise RuntimeError("Local FFmpeg rendering failed")
        result = receipt["result"]
        qa = media_quality.check(run_id)
        if qa["status"] != "VIDEO_PASS" or qa["failures"] or not qa["video_verified"]:
            raise RuntimeError("Rendered video did not pass quality gate")
        _, manifest = _verify_storyboard_manifest(record)
        video_sha = manifest["artifacts"]["video.mp4"]
        if not brain_store.SHA.fullmatch(video_sha):
            raise RuntimeError("Invalid video digest")
        with closing(_db(db_path, create=True)) as db:
            with db:
                changed = db.execute("""UPDATE productions SET
                    status='VIDEO_READY',video_sha=?,render_task_id=?,
                    quality='VIDEO_PASS',updated_at=?
                    WHERE production_id=? AND status='RENDERING'""",
                    (video_sha, receipt["task_id"], _now(), production_id))
                if changed.rowcount != 1:
                    raise RuntimeError("Production receipt changed")
        return {"production_id": production_id, "run_id": run_id,
                "status": "VIDEO_READY", "quality": "VIDEO_PASS",
                "video_sha": video_sha, "video_path": result["video_path"],
                "published": False, "owner_approval_required": True}
    except Exception:
        # Do not replay/overwrite uncertain subprocess output.
        raise


def decide(production_id, choice, video_sha, *, confirm_review=False, db_path=None):
    """Review after owner watches and hears the MP4. This does NOT publish it."""
    if confirm_review is not True or choice not in ("APPROVE", "REJECT"):
        raise PermissionError("Explicit owner review choice required")
    if not isinstance(video_sha, str) or not brain_store.SHA.fullmatch(video_sha):
        raise ValueError("Exact SHA-256 video digest required")
    item = _row(production_id, db_path=db_path)
    if item["status"] != "VIDEO_READY" or item["video_sha"] != video_sha:
        raise PermissionError("Production not ready or video SHA changed")
    _, manifest = _verify_storyboard_manifest(item)
    qa = media_quality.check(item["run_id"])
    if (qa["status"] != "VIDEO_PASS" or qa["failures"]
            or manifest["artifacts"].get("video.mp4") != video_sha):
        raise PermissionError("Video quality or integrity check failed")
    destination = "APPROVED" if choice == "APPROVE" else "REJECTED"
    with closing(_db(db_path, create=True)) as db:
        with db:
            changed = db.execute("""UPDATE productions SET status=?,updated_at=?
               WHERE production_id=? AND status='VIDEO_READY' AND video_sha=?""",
               (destination, _now(), production_id, video_sha))
            if changed.rowcount != 1:
                raise PermissionError("Review was already decided")
    return {"production_id": production_id, "decision": destination,
            "video_sha": video_sha, "published": False, "upload_authorized": False,
            "no_automatic_handoff": True}


def report(*, db_path=None):
    db = _db(db_path)
    if db is None:
        return {"productions": []}
    with closing(db):
        rows = [dict(row) for row in db.execute("""SELECT production_id,source_job_id,
           storyboard_sha,context_sha,run_id,video_sha,status,quality,
           created_at,updated_at FROM productions
           ORDER BY created_at DESC LIMIT 30""")]
    return {"productions": rows, "no_auto_publication": True,
            "model_calls_from_workflow": 0}


def main():
    parser = argparse.ArgumentParser(description="Owner-edited offline video production V1.5")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_cmd = sub.add_parser("prepare")
    prepare_cmd.add_argument("--input-file", required=True)
    prepare_cmd.add_argument("--confirm-edit", action="store_true")
    prepare_cmd.add_argument("--source-job-id")
    prepare_cmd.add_argument("--source-output-sha")
    render_cmd = sub.add_parser("render")
    render_cmd.add_argument("production_id")
    render_cmd.add_argument("--confirm-local-process", action="store_true")
    sub.add_parser("report")
    approval_cmd = sub.add_parser("decide")
    approval_cmd.add_argument("production_id")
    approval_cmd.add_argument("decision", choices=["APPROVE", "REJECT"])
    approval_cmd.add_argument("--video-sha", required=True)
    approval_cmd.add_argument("--confirm-review", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        path = Path(args.input_file)
        brain_store._safe(path)
        if path.stat().st_size > MAX_INPUT:
            parser.error("Storyboard input exceeds 8 KiB")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        output = prepare(data, confirm_edit=args.confirm_edit,
                         source_job_id=args.source_job_id,
                         source_output_sha=args.source_output_sha)
    elif args.command == "render":
        output = render(args.production_id,
                        confirm_local_process=args.confirm_local_process)
    elif args.command == "decide":
        output = decide(args.production_id, args.decision, args.video_sha,
                        confirm_review=args.confirm_review)
    else:
        output = report()
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
