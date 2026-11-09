"""Trusted, allowlisted web skill policies and lazy adapters.

No handler is imported at discovery time. The runner checks grants before dispatch.
"""
POLICY = {
    "web.quality_check": ("product_builder", "read_only",
                          frozenset({"workspace.read"})),
    "web.create": ("product_builder", "owner_gated",
                   frozenset({"model.invoke", "workspace.propose"})),
    "webapp.create": ("product_builder", "owner_gated",
                      frozenset({"model.invoke", "workspace.propose"})),
    "webapp.develop": ("webapp_developer", "owner_gated",
                       frozenset({"model.invoke", "workspace.propose"})),
    "webapp.architect": ("webapp_architect", "owner_gated",
                         frozenset({"model.invoke", "workspace.propose"})),
    "webapp.audit": ("webapp_architect", "read_only",
                     frozenset({"workspace.read"})),
    "webapp.review": ("webapp_reviewer", "owner_gated",
                      frozenset({"model.invoke", "workspace.propose"})),
    "webapp.sandbox_test": ("product_builder", "owner_gated",
                             frozenset({"workspace.read", "process.run"})),
    "web.browser_test": ("product_builder", "owner_gated",
                         frozenset({"workspace.read", "browser.run"})),
}


def dispatch(skill_id, payload):
    if skill_id == "web.quality_check":
        from agentforge.product_quality import check_project
        return check_project(payload["slug"])
    if skill_id == "web.create":
        from agentforge.product_builder import propose
        if "source_proposal_id" in payload:
            return propose(
                payload["slug"], payload["brief"],
                source_proposal_id=payload["source_proposal_id"],
                source_sha256=payload["source_sha256"],
                revision_feedback=payload["revision_feedback"],
            )
        return propose(payload["slug"], payload["brief"])
    if skill_id == "webapp.create":
        from agentforge.webapp_builder import propose
        if "source_proposal_id" in payload:
            return propose(
                payload["slug"], payload["brief"],
                source_proposal_id=payload["source_proposal_id"],
                source_sha256=payload["source_sha256"],
                revision_feedback=payload["revision_feedback"])
        return propose(payload["slug"], payload["brief"])
    if skill_id == "webapp.architect":
        from agentforge.webapp_architect import propose
        return propose(payload["slug"], payload["brief"])
    if skill_id == "webapp.develop":
        from agentforge.webapp_developer import propose
        if "source_proposal_id" in payload:
            return propose(
                payload["slug"], payload["brief"],
                source_proposal_id=payload["source_proposal_id"],
                source_sha256=payload["source_sha256"],
                revision_feedback=payload["revision_feedback"])
        if "architecture_id" in payload:
            return propose(payload["slug"], payload["brief"],
                           architecture_id=payload["architecture_id"],
                           architecture_sha=payload["architecture_sha"])
        return propose(payload["slug"], payload["brief"])
    if skill_id == "webapp.audit":
        from agentforge.webapp_static_qa import audit
        return audit(payload["proposal_id"], payload["sha256"])
    if skill_id == "webapp.review":
        from agentforge.webapp_reviewer import review
        return review(payload["architecture_id"], payload["architecture_sha"],
                      payload["proposal_id"], payload["sha256"],
                      payload["qa_report_id"], payload["qa_report_sha"])
    if skill_id == "webapp.sandbox_test":
        from agentforge.webapp_sandbox import verify
        return verify(payload["proposal_id"], payload["sha256"],
                      confirm_external_run=True)
    if skill_id == "web.browser_test":
        from agentforge.browser_validation import validate
        return validate("project", payload["slug"], confirm_browser_run=True,
                        browser_channel=payload.get("browser_channel", "msedge"))
    raise PermissionError("No trusted adapter")
