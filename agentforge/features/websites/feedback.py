"""Owner feedback → a new supervised website draft Goal, never silent rewriting.

A revision is an independently reviewed website proposal whose execution
must inspect the SHA-verified original and use the owner's full feedback.
The original SHA-valid proposal is retained for audit and comparison.
"""
from uuid import uuid4

from agentforge import brain_planner, goal_preflight, product_builder, workspace_policy

MIN_FEEDBACK = 10
MAX_FEEDBACK = 3000


def request_revision(proposal_id, sha256, feedback, *, brain_db_path=None,
                     analytics_db_path=None, growth_db_path=None,
                     policy_db_path=None):
    if not isinstance(feedback, str) or not MIN_FEEDBACK <= len(feedback.strip()) <= MAX_FEEDBACK:
        raise ValueError("Góp ý cần 10–3000 ký tự.")
    if any(ord(c) < 32 and c not in "\n\t" for c in feedback):
        raise ValueError("Góp ý chứa ký tự điều khiển.")
    doc, _ = product_builder._read_proposal(proposal_id)
    if sha256 != doc["sha256"]:
        raise PermissionError("Proposal SHA không còn trùng khớp.")
    policy = workspace_policy.read(db_path=policy_db_path)
    if not policy["website_enabled"] or policy["max_estimated_model_calls"] < 1:
        raise PermissionError("Role Website hoặc lượt model cho Goal mới đang bị tắt.")

    slug = "rev-" + uuid4().hex[:12]
    # Preserve both complete original intent and requested changes. Neither
    # is squeezed into the old 600-character concatenated pseudo-brief.
    # These source fields are SHA-bound to the new Goal plan.
    inputs = {
        "slug": slug,
        "brief": doc["brief"],
        "source_proposal_id": proposal_id,
        "source_sha256": sha256,
        "revision_feedback": feedback.strip(),
    }
    goal_preflight.require_ready(
        "website.draft", inputs,
        analytics_db_path=analytics_db_path, growth_db_path=growth_db_path)
    goal = brain_planner.propose(
        "Chỉnh sửa landing page từ góp ý owner",
        "website.draft", inputs,
        max_model_calls=1, max_external_runs=0, db_path=brain_db_path)
    return {"status": "PLAN_CREATED", "goal_id": goal["goal_id"],
            "original_proposal_id": proposal_id, "original_sha256": sha256,
            "revision_slug": slug, "model_dispatched": False,
            "approval_required": True, "original_preserved": True}
