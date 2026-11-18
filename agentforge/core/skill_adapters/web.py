"""Trusted, allowlisted web skill policies and lazy adapters.

No handler is imported at discovery time. The runner checks grants before dispatch.
"""
POLICY = {
    "web.quality_check": ("product_builder", "read_only",
                          frozenset({"workspace.read"})),
    "web.create": ("product_builder", "owner_gated",
                   frozenset({"model.invoke", "workspace.propose"})),
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
    if skill_id == "web.browser_test":
        from agentforge.browser_validation import validate
        return validate("project", payload["slug"], confirm_browser_run=True,
                        browser_channel=payload.get("browser_channel", "msedge"))
    raise PermissionError("No trusted adapter")
