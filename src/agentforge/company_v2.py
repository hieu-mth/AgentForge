"""V2 local-first company operating scorecard (evidence-aware, no model calls).

This is an MVP readiness audit, not a guarantee of profits, deployed website,
independent verification, or autonomous corporate operation.
"""
import argparse
import json

from agentforge import autopilot_v13, growth_reports, growth_store
from agentforge import media_workflow_v15, ops_control, quality_v14


def report(*, autopilot_db_path=None, growth_db_path=None, video_db_path=None):
    policy = autopilot_v13.policy(db_path=autopilot_db_path)
    jobs = autopilot_v13.report(db_path=autopilot_db_path)
    inbox = quality_v14.inbox(db_path=autopilot_db_path)
    video = media_workflow_v15.report(db_path=video_db_path)
    campaigns = growth_store.list_campaigns(db_path=growth_db_path, limit=30)
    campaign_reports = [
        growth_reports.report(row["campaign"], db_path=growth_db_path)
        for row in campaigns
    ]
    pending = sum(x["decision"] == "PENDING" for x in inbox["reviews"])
    approved = sum(x["decision"] == "APPROVED" for x in inbox["reviews"])
    videos_ready = sum(x["status"] == "VIDEO_READY" for x in video["productions"])
    videos_approved = sum(x["status"] == "APPROVED" for x in video["productions"])
    leads = sum(x["lead_total"] for x in campaign_reports)
    posts_attested = sum(x["owner_reported_posts"] for x in campaign_reports)
    blocked = []
    if inbox["business_context"] is None:
        blocked.append("SET_BUSINESS_CONTEXT")
    if not campaigns:
        blocked.append("CREATE_REAL_CAMPAIGN")
    if not any(not row["synthetic"] for row in campaigns):
        blocked.append("NO_REAL_CAMPAIGN")
    if videos_approved == 0:
        blocked.append("REVIEW_REAL_MP4")
    if not any(x["lead_total"] for x in campaign_reports if not x["synthetic"]):
        blocked.append("NO_CONSENT_ATTESTED_REAL_LEADS")
    # A campaign/post does not establish a verified sale or revenue.
    operations = ops_control.read()
    if operations["mode"] != "ACTIVE":
        blocked.append("OPERATIONS_PAUSED")
    next_actions = []
    if pending:
        next_actions.append("REVIEW_PENDING_AI_DRAFTS")
    if videos_ready:
        next_actions.append("WATCH_AND_REVIEW_LOCAL_VIDEO")
    if "CREATE_REAL_CAMPAIGN" in blocked:
        next_actions.append("CREATE_OWNER_APPROVED_CAMPAIGN")
    if "NO_CONSENT_ATTESTED_REAL_LEADS" in blocked:
        next_actions.append("TEST_OWNER_CONSENT_LEAD_HANDOFF")
    if videos_approved and not posts_attested:
        next_actions.append("PREPARE_S5_MANUAL_UPLOAD_PACKAGE")
    if not next_actions:
        next_actions.append("REVIEW_OWNER_CAMPAIGN_REPORTS")
    return {
        "version": "2.0", "release_type": "LOCAL_FIRST_MVP_PILOT",
        "operations": operations["mode"],
        "autopilot": {"enabled": policy["enabled"],
                      "daily_call_cap": policy["daily_cap"],
                      "estimated_calls_used_today": jobs["used_today"],
                      "verified_provider_cost": False},
        "content": {"pending_ai_reviews": pending, "approved_ai_drafts": approved,
                    "videos_waiting_for_owner": videos_ready,
                    "owner_approved_local_videos": videos_approved},
        "business": {"campaigns": len(campaigns),
                     "real_campaigns": sum(not c["synthetic"] for c in campaigns),
                     "synthetic_campaigns": sum(bool(c["synthetic"]) for c in campaigns),
                     "owner_recorded_leads": leads,
                     "owner_attested_publications": posts_attested,
                     "externally_verified_publications": 0,
                     "bank_verified_profit_vnd": None,
                     "customer_contacts_stored": False},
        "launch_blockers": blocked,
        "next_owner_actions": next_actions[:5],
        "automated_publication": False, "autonomous_financial_actions": False,
        "real_business_validated": not bool(blocked) and False,
        "disclaimer": "Owner-reviewed offline MVP; real-world conversion and profitability unverified.",
    }


def main():
    parser = argparse.ArgumentParser(description="V2 read-only business readiness scorecard")
    parser.add_argument("command", choices=["report"])
    args = parser.parse_args()
    print(json.dumps(report(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
