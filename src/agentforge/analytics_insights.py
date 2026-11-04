"""S3 deterministic business intelligence over *recorded* user-supplied data.

All rates are explicitly denominator-scoped. Neither synthetic examples nor
owner-confirmed receipts are third-party verified revenue or causal proof.
"""
from collections import defaultdict
from math import sqrt

from agentforge import analytics_store as store

METRICS = ("impressions", "views", "clicks", "leads", "orders", "watch_seconds")


def _rate(num, den):
    return round(num / den, 6) if den else None


def _aggregate(rows):
    totals = {key: sum(item[key] for item in rows) for key in METRICS}
    totals.update({
        "ctr_clicks_per_impression": _rate(totals["clicks"], totals["impressions"]),
        "view_rate_views_per_impression": _rate(totals["views"], totals["impressions"]),
        "leads_per_click": _rate(totals["leads"], totals["clicks"]),
        "orders_per_lead": _rate(totals["orders"], totals["leads"]),
        "average_watch_seconds_per_view": _rate(totals["watch_seconds"], totals["views"]),
        "observation_rows": len(rows),
    })
    return totals


def _lineage(data):
    return {
        "dataset": data["dataset"], "campaign": data["campaign"],
        "synthetic": data["synthetic"],
        "source_files": [
            {"filename": x["filename"], "sha256": x["sha256"],
             "source_kind": x["source_kind"], "imported_at": x["imported_at"],
             "kind": x["kind"], "rows": x["row_count"]}
            for x in data["imports"]
        ],
        "source_count": len(data["imports"]),
        "external_verification": False,
    }


def _common_uncertainty(data):
    warnings = [
        "User-supplied CSV, not a live platform API; metrics have not been independently verified.",
        "Platform-defined views/impressions/clicks may differ; do not assume unique people.",
    ]
    if data["synthetic"]:
        warnings.insert(0, "SYNTHETIC DEMO DATA — never use these values as actual business results.")
    if not data["performance"]:
        warnings.append("No daily performance observations for this selection.")
    if any(r["views"] > r["impressions"] for r in data["performance"]):
        warnings.append(
            "Some views exceed impressions. These metrics may use different platform definitions."
        )
    if any(r["clicks"] and not r["leads"] for r in data["performance"]):
        warnings.append("Some clicks have no recorded leads; tracking or funnel drop-off is unknown.")
    return warnings


def data_quality(dataset, *, campaign=None, db_path=None):
    data = store.load_data(dataset, campaign=campaign, db_path=db_path)
    warnings = _common_uncertainty(data)
    if not data["imports"]:
        warnings.append("Dataset has no source files")
    if data["performance"] and len({x["date"] for x in data["performance"]}) < 3:
        warnings.append("Fewer than three observed dates; trend interpretation is weak.")
    if data["ledger"] and not any(r["status"] == "owner_confirmed" for r in data["ledger"]):
        warnings.append("No owner-confirmed ledger entries; cash figures remain pending.")
    return {
        "status": "REVIEW_REQUIRED" if warnings else "PASS",
        "dataset": dataset, "synthetic": data["synthetic"],
        "performance_rows": len(data["performance"]),
        "ledger_rows": len(data["ledger"]),
        "warnings": warnings, "sources": _lineage(data),
        "financial_verification": False,
    }


def content_report(dataset, *, campaign=None, db_path=None):
    data = store.load_data(dataset, campaign=campaign, db_path=db_path)
    rows = data["performance"]
    by_channel = {}
    for channel in sorted({x["channel"] for x in rows}):
        by_channel[channel] = _aggregate([x for x in rows if x["channel"] == channel])
    total = _aggregate(rows)
    diagnostics = []
    if not rows:
        diagnostics.append("Import performance observations before interpreting content.")
    elif total["impressions"] == 0:
        diagnostics.append("Recorded impressions are zero; no CTR can be computed.")
    else:
        if total["ctr_clicks_per_impression"] is not None and total["ctr_clicks_per_impression"] < .01:
            diagnostics.append(
                "Recorded CTR is under 1%; inspect topic, packaging, distribution and tracking."
            )
        if total["clicks"] >= 30 and total["leads"] == 0:
            diagnostics.append(
                "Clicks without recorded leads; inspect landing, intent and attribution."
            )
        if total["leads"] >= 20 and total["orders"] == 0:
            diagnostics.append(
                "Leads without recorded orders; inspect follow-up and reporting gaps."
            )
        if total["impressions"] < 100:
            diagnostics.append("Under 100 recorded impressions; directional only.")
    return {
        "status": "ANALYZED_WITH_UNCERTAINTY", "dataset": dataset,
        "campaign": campaign, "synthetic": data["synthetic"],
        "metrics": total, "by_channel": by_channel,
        "diagnostics": diagnostics,
        "uncertainty": _common_uncertainty(data),
        "sources": _lineage(data),
        "causal_claim": False,
    }


def trend_report(dataset, *, campaign=None, db_path=None):
    data = store.load_data(dataset, campaign=campaign, db_path=db_path)
    rows = data["performance"]
    by_day = []
    for day in sorted({r["date"] for r in rows}):
        group = [r for r in rows if r["date"] == day]
        by_day.append({"date": day, **_aggregate(group)})
    if len(by_day) < 3:
        interpretation = "INSUFFICIENT_DATES"
        signal = None
    else:
        latest, previous = by_day[-1], by_day[-2]
        signal = {
            "latest_date": latest["date"],
            "previous_observed_date": previous["date"],
            "views_change": latest["views"] - previous["views"],
            "clicks_change": latest["clicks"] - previous["clicks"],
            "relative_views_change": (
                _rate(latest["views"] - previous["views"], previous["views"])
            ),
        }
        interpretation = "DESCRIPTIVE_ONLY"
    uncertainty = _common_uncertainty(data)
    uncertainty.append(
        "Observed dates can have gaps; change in totals does not isolate market demand, "
        "content quality or algorithmic distribution."
    )
    return {
        "status": "ANALYZED_WITH_UNCERTAINTY", "dataset": dataset,
        "campaign": campaign, "synthetic": data["synthetic"],
        "series": by_day, "signal": signal,
        "interpretation": interpretation,
        "uncertainty": uncertainty, "sources": _lineage(data),
        "external_market_trend_verified": False,
    }


def _wilson(clicks, impressions):
    """Wilson 95% interval, descriptive only; not valid for all traffic designs."""
    if not impressions or clicks > impressions:
        return None
    n, p, z = impressions, clicks / impressions, 1.96
    base = 1 + z*z/n
    middle = (p + z*z/(2*n))/base
    radius = z*sqrt((p*(1-p) + z*z/(4*n))/n)/base
    return [round(max(0, middle-radius), 6), round(min(1, middle+radius), 6)]


def experiment_report(dataset, campaign, *, db_path=None):
    data = store.load_data(dataset, campaign=campaign, db_path=db_path)
    rows = data["performance"]
    variants = sorted({r["variant"] for r in rows})
    if len(variants) != 2:
        raise store.AnalyticsError("Experiment requires exactly two recorded variants")
    channels = {r["channel"] for r in rows}
    if len(channels) != 1:
        raise store.AnalyticsError("Experiment variants must share exactly one channel")
    report = {}
    days = []
    for variant in variants:
        sample = [r for r in rows if r["variant"] == variant]
        totals = _aggregate(sample)
        totals["ctr_wilson_95_approx"] = _wilson(totals["clicks"], totals["impressions"])
        report[variant] = totals
        days.append({r["date"] for r in sample})
    shared_dates = sorted(days[0] & days[1])
    sufficient = (len(shared_dates) >= 2 and
                  all(x["impressions"] >= 100 for x in report.values()) and
                  all(x["clicks"] <= x["impressions"] for x in report.values()))
    delta = None
    if all(x["ctr_clicks_per_impression"] is not None for x in report.values()):
        delta = round(
            report[variants[1]]["ctr_clicks_per_impression"] -
            report[variants[0]]["ctr_clicks_per_impression"], 6
        )
    warnings = _common_uncertainty(data)
    if not sufficient:
        warnings.append(
            "Insufficient comparable exposure/overlapping dates or incompatible click counts."
        )
    warnings.append(
        "Not a randomized controlled test; confidence intervals assume independent "
        "impressions and do not establish a winning variant or causality."
    )
    return {
        "status": "DESCRIPTIVE_ONLY", "dataset": dataset, "campaign": campaign,
        "synthetic": data["synthetic"], "channel": next(iter(channels)),
        "variants": report, "variant_order": variants,
        "ctr_absolute_delta_second_minus_first": delta,
        "overlapping_dates": shared_dates, "descriptive_sample_sufficient": sufficient,
        "recommended_winner": None, "causal_claim": False,
        "uncertainty": warnings, "sources": _lineage(data),
    }


def finance_report(dataset, *, campaign=None, db_path=None):
    data = store.load_data(dataset, campaign=campaign, db_path=db_path)
    ledger = data["ledger"]
    def total(kind, status):
        return sum(r["amount_vnd"] for r in ledger
                   if r["kind"] == kind and r["status"] == status)
    received = total("revenue", "owner_confirmed")
    paid = total("cost", "owner_confirmed")
    pending_revenue = total("revenue", "pending")
    pending_cost = total("cost", "pending")
    warnings = [
        "owner_confirmed means entered/attested by owner, NOT bank/platform reconciled.",
        "Pending revenue is NOT cash received and must not enter recorded net cash.",
        "Actual net profit needs reconciled transactions, taxes, returns and complete costs.",
    ]
    if data["synthetic"]:
        warnings.insert(0, "SYNTHETIC DEMO DATA — no real money has been observed.")
    if not ledger:
        warnings.append("No ledger entries for this campaign/dataset")
    return {
        "status": "OWNER_RECORDED_NOT_VERIFIED", "dataset": dataset,
        "campaign": campaign, "synthetic": data["synthetic"],
        "currency": "VND", "transactions": len(ledger),
        "owner_confirmed_received_vnd": received,
        "owner_confirmed_paid_vnd": paid,
        "owner_recorded_net_cash_vnd": received - paid,
        "pending_revenue_vnd": pending_revenue,
        "pending_cost_vnd": pending_cost,
        "verified_net_profit_vnd": None,
        "bank_reconciled": False, "uncertainty": warnings,
        "sources": _lineage(data),
    }
