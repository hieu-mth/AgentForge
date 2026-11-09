"""Trusted, allowlisted analytics skill policies and lazy adapters.

No handler is imported at discovery time. The runner checks grants before dispatch.
"""
POLICY = {
    "analytics.import": ("analytics_analyst", "owner_gated",
                         frozenset({"workspace.write"})),
    "analytics.quality_check": ("analytics_analyst", "read_only",
                                frozenset({"workspace.read"})),
    "analytics.content_report": ("analytics_analyst", "read_only",
                                 frozenset({"workspace.read"})),
    "analytics.trend_report": ("analytics_analyst", "read_only",
                               frozenset({"workspace.read"})),
    "analytics.experiment_report": ("analytics_analyst", "read_only",
                                    frozenset({"workspace.read"})),
    "analytics.finance_report": ("analytics_analyst", "read_only",
                                 frozenset({"workspace.read"})),
    "analytics.opportunity_score": ("analytics_analyst", "read_only",
                                    frozenset({"workspace.read"})),
}


def dispatch(skill_id, payload):
    if skill_id == "analytics.import":
        from agentforge.analytics_store import import_csv
        return import_csv(payload["dataset"], payload["kind"], payload["filename"],
                          source_kind=payload["source_kind"],
                          synthetic=payload["synthetic"], confirm_write=True)
    if skill_id.startswith("analytics."):
        from agentforge import analytics_insights as insights
        dataset, campaign = payload["dataset"], payload.get("campaign")
        if skill_id == "analytics.content_report":
            return insights.content_report(dataset, campaign=campaign)
        if skill_id == "analytics.trend_report":
            return insights.trend_report(dataset, campaign=campaign)
        if skill_id == "analytics.finance_report":
            return insights.finance_report(dataset, campaign=campaign)
        if skill_id == "analytics.quality_check":
            return insights.data_quality(dataset, campaign=campaign)
        if skill_id == "analytics.experiment_report":
            return insights.experiment_report(dataset, campaign)
        if skill_id == "analytics.opportunity_score":
            return insights.opportunity_report(dataset, campaign=campaign)
    raise PermissionError("No trusted adapter")
