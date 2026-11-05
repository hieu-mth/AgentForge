"""S5 read-only, traceable funnel, handoff-quality and owner-books crosscheck.

No revenue figure here is independently reconciled to a bank or platform.
"""
from collections import Counter
from pathlib import Path

from agentforge import growth_store as store


def report(campaign, *, db_path=None):
    records = store.load_campaign(campaign, db_path=db_path)
    info = records["campaign"]
    leads = Counter(row["status"] for row in records["leads"])
    packages = records["packages"]
    money = records["money"]
    def total(kind, status):
        return sum(x["amount_vnd"] for x in money
                   if x["kind"] == kind and x["status"] == status)
    received = total("commission", "owner_confirmed")
    paid = total("cost", "owner_confirmed")
    pending = total("commission", "pending")
    held = total("cost", "pending")
    committed_costs = paid + held
    notes = [
        "Post URLs are entered by owner; platform publication is NOT independently verified.",
        "Lead counts are manual, consent-attested and do not prove attributed conversions.",
        "owner_confirmed means owner-recorded; bank, affiliate platform and refund checks absent.",
        "Budget checks cap only owner-recorded cost rows, NOT actual provider billing or ad spend.",
    ]
    if info["synthetic"]:
        notes.insert(0, "SYNTHETIC DEMO: leads, postings and cash do not represent real business.")
    if not info["analytics_dataset"]:
        notes.append("No S3 dataset linked; growth records are not tied to traffic observations.")
    return {
        "status": "OWNER_RECORDED_UNVERIFIED",
        "campaign": campaign, "synthetic": bool(info["synthetic"]),
        "title": info["title"], "analytics_dataset": info["analytics_dataset"] or "",
        "lead_total": len(records["leads"]),
        "lead_counts": {k: leads.get(k, 0) for k in store.LEAD_TRANSITIONS},
        "packages_ready_for_manual_upload": sum(
            x["status"] == "READY_FOR_OWNER_UPLOAD" for x in packages),
        "owner_reported_posts": len(records["posts"]),
        "platform_verified_posts": 0,
        "package_count": len(packages),
        "currency": "VND",
        "owner_confirmed_commission_vnd": received,
        "owner_confirmed_cost_vnd": paid,
        "pending_commission_vnd": pending,
        "pending_cost_vnd": held,
        "owner_recorded_net_cash_vnd": received - paid,
        "owner_budget_cap_vnd": info["budget_vnd"],
        "booked_cost_vnd": committed_costs,
        "bookkeeping_budget_remaining_vnd": info["budget_vnd"] - committed_costs,
        "verified_net_profit_vnd": None,
        "bank_reconciled": False, "platform_api_connected": False,
        "marketing_roi_verified": False,
        "uncertainty": notes,
    }


def quality_check(campaign, *, db_path=None):
    data = store.load_campaign(campaign, db_path=db_path)
    findings = []
    def fail(rule):
        findings.append({"rule": rule, "severity": "FAIL"})
    def warn(rule):
        findings.append({"rule": rule, "severity": "WARN"})
    for bundle in data["packages"]:
        file = Path(bundle["package_path"])
        try:
            store._safe(file)
            if (not file.is_file() or file.stat().st_size > 165_000_000):
                fail("bundle_missing_or_oversized")
                continue
            from agentforge.growth_bundle import _sha
            if _sha(file) != bundle["sha256"]:
                fail("bundle_hash_mismatch")
        except (OSError, store.GrowthError):
            fail("bundle_inaccessible")
    if not data["packages"]:
        warn("no_manual_upload_packages")
    if not data["posts"]:
        warn("no_owner_attested_posts")
    else:
        warn("posts_not_platform_verified")
    if data["campaign"]["synthetic"]:
        warn("synthetic_demo_not_business_results")
    if not data["campaign"]["analytics_dataset"]:
        warn("no_s3_analytics_link")
    if any(x["status"] == "pending" and x["kind"] == "commission"
           for x in data["money"]):
        warn("commission_pending_not_realized")
    failures = sum(x["severity"] == "FAIL" for x in findings)
    warnings = sum(x["severity"] == "WARN" for x in findings)
    return {"status": "FAIL" if failures else "REVIEW_REQUIRED" if warnings else "PASS",
            "campaign": campaign, "synthetic": bool(data["campaign"]["synthetic"]),
            "failures": failures, "warnings": warnings, "findings": findings,
            "verified_publication": False,
            "verified_revenue": False}


def reconcile(campaign, *, db_path=None, analytics_db_path=None):
    """Match two owner's ledgers, never claim independent financial truth."""
    records = store.load_campaign(campaign, db_path=db_path)
    info = records["campaign"]
    base = {"campaign": campaign, "synthetic": bool(info["synthetic"]),
            "source_dataset": info["analytics_dataset"] or "",
            "bank_reconciled": False, "platform_reconciled": False,
            "verified_net_profit_vnd": None}
    if not info["analytics_dataset"]:
        return {**base, "status": "NO_S3_DATASET",
                "matched": 0, "missing": 0, "mismatched": 0,
                "unlinked": len(records["money"]),
                "uncertainty": ["No S3 ledger to compare."]}
    from agentforge import analytics_store
    prior = analytics_store._connect(analytics_db_path)
    if prior is None:
        return {**base, "status": "S3_DATA_UNAVAILABLE",
                "matched": 0, "missing": 0, "mismatched": 0,
                "unlinked": len(records["money"]),
                "uncertainty": ["S3 local database not present."]}
    import contextlib
    linked = []
    with contextlib.closing(prior) as conn:
        check = conn.execute(
            "SELECT synthetic FROM datasets WHERE dataset=?",
            (info["analytics_dataset"],)).fetchone()
        if check is None or bool(check["synthetic"]) != bool(info["synthetic"]):
            return {**base, "status": "S3_PROVENANCE_MISMATCH",
                    "matched": 0, "missing": 0, "mismatched": 0,
                    "unlinked": len(records["money"]),
                    "uncertainty": ["S3 dataset missing or synthetic classification differs."]}
        for entry in records["money"]:
            if not entry["s3_tx_id"]:
                continue
            row = conn.execute(
                "SELECT campaign,kind,status,amount_vnd FROM ledger "
                "WHERE dataset=? AND tx_id=?",
                (info["analytics_dataset"], entry["s3_tx_id"])).fetchone()
            expected_kind = "revenue" if entry["kind"] == "commission" else "cost"
            if row is None:
                linked.append("missing")
            elif (row["campaign"] == campaign and row["kind"] == expected_kind
                  and row["status"] == entry["status"]
                  and row["amount_vnd"] == entry["amount_vnd"]):
                linked.append("matched")
            else:
                linked.append("mismatched")
    totals = Counter(linked)
    unlinked = sum(not x["s3_tx_id"] for x in records["money"])
    status = ("OWNER_BOOKS_MATCH_NOT_BANK_VERIFIED"
              if linked and not (totals["missing"] or totals["mismatched"] or unlinked)
              else "REVIEW_REQUIRED")
    return {
        **base, "status": status,
        "matched": totals["matched"], "missing": totals["missing"],
        "mismatched": totals["mismatched"], "unlinked": unlinked,
        "uncertainty": [
            "Only matches owner-entered S5 records to owner-imported S3 entries.",
            "Match does not prove payment, platform views, taxes, commissions or true net profit.",
        ] + (["SYNTHETIC DEMO: matched numbers are fabricated test evidence."]
             if info["synthetic"] else []),
    }
