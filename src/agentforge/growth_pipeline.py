"""S5 Growth Operations CLI: offline campaign/handoff, ledger, funnel and demo.

No platform accounts connected, no network posting or payment. The demo
runs real local FFmpeg only with explicit owner confirmation and marks ALL
business records SYNTHETIC.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from agentforge import growth_store as store
from agentforge import skill_runner

REPORT_SKILLS = {
    "report": "growth.report",
    "quality": "growth.quality_check",
    "reconcile": "growth.reconcile",
}


def _read_json(path):
    source = Path(path)
    store._safe(source)
    if not source.is_file() or source.stat().st_size > 8192:
        raise store.GrowthError("JSON input must be a regular file <= 8KB")
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise store.GrowthError("Input must be a JSON object")
    return data


def _invoke(skill_id, payload, *, grants=(), confirm_external_run=False):
    return skill_runner.invoke(skill_id, payload, grants=grants,
                               confirm_external_run=confirm_external_run)


def _need_success(result, label):
    if result["status"] != "SUCCEEDED":
        raise RuntimeError(f"S5 {label} was not approved or did not succeed")
    return result["result"]


def demo(*, confirm_local_media=False):
    """One full offline vertical slice joining S2 -> S3 -> S4 -> S5."""
    if confirm_local_media is not True:
        raise PermissionError("Explicit --confirm-local-media required for FFmpeg")
    from agentforge import analytics_pipeline
    from agentforge import brain_planner, brain_store, brain_runner
    seed = analytics_pipeline.synthetic_demo()
    if seed["status"] != "SUCCEEDED" or seed["synthetic"] is not True:
        raise RuntimeError("S3 synthetic seed failed")
    campaign = "demo-nem-" + uuid4().hex[:10]
    created = _need_success(_invoke("growth.campaign_create", {
        "campaign": campaign, "title": "Synthetic mattress campaign",
        "analytics_dataset": seed["dataset"], "budget_vnd": 80000,
        "synthetic": True, "confirm_write": True,
    }, grants=("workspace.write",)), "campaign create")
    storyboard = {
        "slug": "nem-growth-demo", "title": "Tư vấn nệm mẫu",
        "scenes": [
            {"headline": "Chọn nệm theo nhu cầu",
             "caption": "Xác định nhu cầu và kích thước trước khi chọn.",
             "duration_seconds": 3},
            {"headline": "Tư vấn trước khi mua",
             "caption": "Hỏi về độ nâng đỡ và cảm giác nằm phù hợp.",
             "duration_seconds": 3},
        ],
    }
    composed = _need_success(_invoke(
        "media.compose", storyboard, grants=("workspace.write",)), "S2 compose")
    video = _need_success(_invoke(
        "media.video_render", {
            "run_id": composed["run_id"], "confirm_external_run": True,
        }, grants=("workspace.write", "process.run"),
        confirm_external_run=True), "S2 video")
    bundles = []
    for channel in ("youtube", "tiktok"):
        receipt = _need_success(_invoke("growth.bundle_prepare", {
            "campaign": campaign, "channel": channel,
            "run_id": composed["run_id"],
            "title": "Gợi ý lựa chọn nệm phù hợp",
            "description": "Video giới thiệu các yếu tố nên cân nhắc khi chọn nệm.",
            "confirm_rights": True, "confirm_write": True,
        }, grants=("workspace.write",)), "channel bundle")
        bundles.append(receipt)
    lead = _need_success(_invoke("growth.record_event", {
        "kind": "lead_new", "data": {"campaign": campaign,
                                    "channel": "youtube", "consent_confirmed": True},
        "confirm_write": True,
    }, grants=("workspace.write",)), "synthetic lead")
    pending = _need_success(_invoke("growth.record_event", {
        "kind": "money",
        "data": {"campaign": campaign, "tx_id": "synthetic-commission-1",
                 "kind": "commission", "status": "pending",
                 "amount_vnd": 60000, "evidence_ref": "", "s3_tx_id": ""},
        "confirm_write": True,
    }, grants=("workspace.write",)), "synthetic pending income")
    paid = _need_success(_invoke("growth.record_event", {
        "kind": "money",
        "data": {"campaign": campaign, "tx_id": "synthetic-cost-1",
                 "kind": "cost", "status": "owner_confirmed",
                 "amount_vnd": 15000, "evidence_ref": "synthetic:demo-cost",
                 "s3_tx_id": ""},
        "confirm_write": True,
    }, grants=("workspace.write",)), "synthetic cost")
    reports = {name: _need_success(
        _invoke(skill_id, {"campaign": campaign}), name)
        for name, skill_id in REPORT_SKILLS.items()}
    plan = brain_planner.propose(
        "Review synthetic channel growth", "growth.review",
        {"campaign": campaign})
    brain_store.approve_goal(plan["goal_id"], plan["plan_sha256"])
    delegated = brain_runner.execute(plan["goal_id"])
    if delegated["status"] != "SUCCEEDED":
        raise RuntimeError("S4 growth review delegation failed")
    return {
        "status": "SUCCEEDED", "synthetic": True,
        "campaign": campaign, "s3_dataset": seed["dataset"],
        "media_run_id": composed["run_id"], "video_path": video["video_path"],
        "packages": bundles, "lead_id": lead["lead_id"],
        "recorded_pending_vnd": pending["amount_vnd"],
        "recorded_cost_vnd": paid["amount_vnd"],
        "reports": reports,
        "goal_id": plan["goal_id"], "goal_completed_steps": delegated["executed_steps"],
        "manual_upload_required": True, "post_count": 0,
        "platform_api_connected": False, "revenue_verified": False,
        "bank_reconciled": False, "autonomous_publishing": False,
    }


def main():
    cli = argparse.ArgumentParser(description="S5 local-first Revenue & Growth MVP")
    sub = cli.add_subparsers(dest="command", required=True)
    demo_cmd = sub.add_parser("demo")
    demo_cmd.add_argument("--confirm-local-media", action="store_true")
    sub.add_parser("campaigns")
    campaign = sub.add_parser("campaign-create")
    campaign.add_argument("--input-file", required=True)
    campaign.add_argument("--confirm-write", action="store_true")
    bundle = sub.add_parser("bundle")
    bundle.add_argument("--input-file", required=True)
    bundle.add_argument("--confirm-write", action="store_true")
    bundle.add_argument("--confirm-rights", action="store_true")
    event = sub.add_parser("record-event")
    event.add_argument("--input-file", required=True)
    event.add_argument("--confirm-write", action="store_true")
    for name in REPORT_SKILLS:
        sub.add_parser(name).add_argument("campaign")
    args = cli.parse_args()
    if args.command == "demo":
        result = demo(confirm_local_media=args.confirm_local_media)
    elif args.command == "campaigns":
        result = {"status": "OK", "campaigns": store.list_campaigns()}
    elif args.command == "campaign-create":
        payload = _read_json(args.input_file)
        payload["confirm_write"] = args.confirm_write
        result = _invoke("growth.campaign_create", payload,
                         grants=("workspace.write",) if args.confirm_write else ())
    elif args.command == "bundle":
        payload = _read_json(args.input_file)
        payload.update(confirm_write=args.confirm_write,
                       confirm_rights=args.confirm_rights)
        result = _invoke("growth.bundle_prepare", payload,
                         grants=("workspace.write",) if args.confirm_write else ())
    elif args.command == "record-event":
        payload = _read_json(args.input_file)
        payload["confirm_write"] = args.confirm_write
        result = _invoke("growth.record_event", payload,
                         grants=("workspace.write",) if args.confirm_write else ())
    else:
        result = _invoke(REPORT_SKILLS[args.command], {"campaign": args.campaign})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "FAILED":
        cli.exit(2)
    if result["status"] == "WAITING_APPROVAL":
        cli.exit(3)
    if args.command == "quality" and result["result"]["status"] == "FAIL":
        cli.exit(2)


if __name__ == "__main__":
    main()
