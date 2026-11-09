"""Trusted, allowlisted growth skill policies and lazy adapters.

No handler is imported at discovery time. The runner checks grants before dispatch.
"""
POLICY = {
    "growth.campaign_create": ("growth_operator", "owner_gated",
                               frozenset({"workspace.write"})),
    "growth.bundle_prepare": ("growth_operator", "owner_gated",
                              frozenset({"workspace.write"})),
    "growth.record_event": ("growth_operator", "owner_gated",
                            frozenset({"workspace.write"})),
    "growth.report": ("growth_operator", "read_only",
                      frozenset({"workspace.read"})),
    "growth.quality_check": ("growth_operator", "read_only",
                             frozenset({"workspace.read"})),
    "growth.reconcile": ("growth_operator", "read_only",
                         frozenset({"workspace.read"})),
}


def dispatch(skill_id, payload):
    if skill_id == "growth.campaign_create":
        from agentforge.growth_store import create_campaign
        return create_campaign(
            {key: value for key, value in payload.items() if key != "confirm_write"},
            confirm_write=True)
    if skill_id == "growth.bundle_prepare":
        from agentforge.growth_bundle import prepare
        return prepare(payload["campaign"], payload["channel"], payload["run_id"],
                       payload["title"], payload["description"],
                       confirm_rights=True, confirm_write=True)
    if skill_id == "growth.record_event":
        from agentforge.growth_store import record_event
        return record_event(payload["kind"], payload["data"], confirm_write=True)
    if skill_id.startswith("growth."):
        from agentforge import growth_reports
        campaign = payload["campaign"]
        if skill_id == "growth.report":
            return growth_reports.report(campaign)
        if skill_id == "growth.quality_check":
            return growth_reports.quality_check(campaign)
        if skill_id == "growth.reconcile":
            return growth_reports.reconcile(campaign)
    raise PermissionError("No trusted adapter")
