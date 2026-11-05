"""Explicit, bounded read-only public result projection for Control Center.

Never return whole task results or arbitrary model output. This module only
projects known statistical/finance fields; it cannot serialize source CSV rows,
PII, prompts, model text, paths, or source filenames. Synthetic provenance is
always displayed. The raw result remains in the owner-local task database.
"""

ANALYTICS = frozenset({
    "analytics.quality_check", "analytics.content_report",
    "analytics.trend_report", "analytics.experiment_report",
    "analytics.finance_report", "analytics.opportunity_score",
})
GROWTH = frozenset({"growth.report", "growth.quality_check", "growth.reconcile"})
SCALARS = frozenset({
    "status", "dataset", "campaign", "synthetic",
    "performance_rows", "ledger_rows", "transactions", "currency",
    "financial_verification", "bank_reconciled", "causal_claim",
    "score_is_heuristic", "market_demand_verified", "scale_authorized",
    "owner_confirmed_received_vnd", "owner_confirmed_paid_vnd",
    "owner_recorded_net_cash_vnd", "pending_revenue_vnd",
    "pending_cost_vnd", "verified_net_profit_vnd",
    "interpretation", "external_market_trend_verified",
    "lead_total", "package_count", "owner_reported_posts",
    "owner_confirmed_commission_vnd", "owner_confirmed_cost_vnd",
    "owner_budget_cap_vnd", "platform_api_connected",
})
NUMERIC = frozenset({
    "impressions", "views", "clicks", "leads", "orders",
    "watch_seconds", "ctr_clicks_per_impression",
    "view_rate_views_per_impression", "leads_per_click",
    "orders_per_lead", "average_watch_seconds_per_view",
    "observation_rows", "investigation_score_0_100",
})
SIGNALS = NUMERIC | frozenset({"channel", "classification"})
WARNINGS = ("warnings", "uncertainty", "diagnostics")


def _scalar(value):
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, str):
        return value[:160]
    return None


def _picked(data, names):
    if not isinstance(data, dict):
        return {}
    return {k: _scalar(data[k]) for k in sorted(names & data.keys())
            if type(data[k]) in (str, int, float, bool) or data[k] is None}


def present(skill_id, result):
    """Return only preapproved owner-visible statistics; no raw result fallback."""
    if not isinstance(result, dict):
        return None
    if skill_id in ANALYTICS:
        kind = "analytics"
    elif skill_id in GROWTH:
        kind = "growth"
    else:
        return None
    view = {
        "kind": kind,
        "fields": _picked(result, SCALARS),
        "metrics": _picked(result.get("metrics"), NUMERIC),
        "channels": [],
        "signals": [],
        "notices": [],
        "source_count": None,
        "business_verified": False,
    }
    by_channel = result.get("by_channel")
    if isinstance(by_channel, dict):
        for name, metrics in sorted(by_channel.items())[:12]:
            if isinstance(name, str) and isinstance(metrics, dict):
                view["channels"].append({
                    "name": name[:50], "metrics": _picked(metrics, NUMERIC)})
    signals = result.get("signals")
    if isinstance(signals, list):
        view["signals"] = [_picked(x, SIGNALS) for x in signals[:12]
                           if isinstance(x, dict)]
    for key in WARNINGS:
        raw = result.get(key)
        if isinstance(raw, list):
            view["notices"].extend(
                item[:320] for item in raw[:12]
                if isinstance(item, str))
    view["notices"] = view["notices"][:20]
    lineage = result.get("sources")
    if isinstance(lineage, dict) and type(lineage.get("source_count")) is int:
        view["source_count"] = max(0, min(lineage["source_count"], 1000))
    return view
