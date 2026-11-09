"""Owner feedback opens a new SHA-reviewed application Goal; no background execution."""
from uuid import uuid4

from agentforge import brain_planner, goal_preflight, webapp_builder, workspace_policy, webapp_developer


def request_revision(proposal_id, sha256, feedback, *, brain_db_path=None,
                     analytics_db_path=None, growth_db_path=None,
                     policy_db_path=None):
    from agentforge.website_feedback import MIN_FEEDBACK, MAX_FEEDBACK
    if (not isinstance(feedback, str)
            or not MIN_FEEDBACK <= len(feedback.strip()) <= MAX_FEEDBACK
            or any(ord(c) < 32 and c not in "\n\t" for c in feedback)):
        raise ValueError("Góp ý ứng dụng cần 10–3000 ký tự hợp lệ.")
    provider = webapp_developer.provider(proposal_id)
    doc, _ = provider._read_proposal(proposal_id)
    if doc["sha256"] != sha256:
        raise PermissionError("APP_SOURCE_STALE: app proposal SHA no longer matches")
    policy = workspace_policy.read(db_path=policy_db_path)
    if not policy["website_enabled"] or policy["max_estimated_model_calls"] < 1:
        raise PermissionError("Workflow ứng dụng hoặc số lượt model đã bị Owner tắt.")
    slug = "revision-" + uuid4().hex[:12]
    inputs = {
        "slug": slug,
        "brief": doc["brief"],
        "source_proposal_id": proposal_id,
        "source_sha256": sha256,
        "revision_feedback": feedback.strip(),
    }
    template = ("webapp.revision" if provider is webapp_builder
                else "webapp.source_revision")
    goal_preflight.require_ready(
        template, inputs,
        analytics_db_path=analytics_db_path, growth_db_path=growth_db_path)
    goal = brain_planner.propose(
        ("Chỉnh sửa dữ liệu marketplace (không chạy mã)" if provider is webapp_builder
         else "Chỉnh sửa source React từ phiên bản đã duyệt SHA"),
        template, inputs,
        max_model_calls=1, max_external_runs=0, db_path=brain_db_path)
    return {
        "status": "PLAN_CREATED", "goal_id": goal["goal_id"],
        "original_proposal_id": proposal_id, "original_sha256": sha256,
        "revision_slug": slug,
        "approval_required": True, "model_dispatched": False,
        "original_preserved": True,
    }
