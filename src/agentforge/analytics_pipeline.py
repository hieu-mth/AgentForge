"""S3 analytics CLI: real CSV import, deterministic insight skills, demo pilot.

No model, external platform API, posting, ad spending or bank connection.
Demo data is unmistakably synthetic and isolated in its own dataset.
"""
import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from agentforge import analytics_store as store
from agentforge import skill_runner

REPORT_SKILLS = {
    "content": "analytics.content_report",
    "trend": "analytics.trend_report",
    "experiment": "analytics.experiment_report",
    "finance": "analytics.finance_report",
    "quality": "analytics.quality_check",
    "opportunity": "analytics.opportunity_score",
}


def _write_demo_csv(prefix, columns, rows):
    store._safe_path(store.INBOX)
    store.INBOX.mkdir(parents=True, exist_ok=True)
    name = f"s3-{prefix}-{uuid4().hex[:12]}.csv"
    path = store.INBOX / name
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return name


def _run(skill, payload, *, grants=()):
    return skill_runner.invoke(skill, payload, grants=grants)


def synthetic_demo():
    """Exercise a full local import -> 5 reports pipeline; NEVER real data."""
    dataset = "demo-" + uuid4().hex[:10]
    today = date.today() - timedelta(days=1)
    performance = []
    for day_number in range(4):
        day = (today - timedelta(days=3-day_number)).isoformat()
        for variant, impressions, clicks in [
            ("A", 600 + 80*day_number, 21 + day_number),
            ("B", 580 + 80*day_number, 29 + 2*day_number),
        ]:
            performance.append({
                "date": day, "campaign": "nem-shorts",
                "channel": "youtube", "content": "clip-" + variant.lower(),
                "variant": variant, "impressions": impressions,
                "views": round(impressions*.45), "clicks": clicks,
                "leads": 3 + day_number, "orders": day_number // 2,
                "watch_seconds": (round(impressions*.45))*9,
            })
    transactions = [
        {"tx_id": "s3-demo-receipt-1", "date": today.isoformat(),
         "campaign": "nem-shorts", "kind": "revenue", "status": "owner_confirmed",
         "amount_vnd": 150000, "evidence_ref": "synthetic-demo-receipt"},
        {"tx_id": "s3-demo-cost-1", "date": today.isoformat(),
         "campaign": "nem-shorts", "kind": "cost", "status": "owner_confirmed",
         "amount_vnd": 55000, "evidence_ref": "synthetic-demo-spend"},
        {"tx_id": "s3-demo-pending-1", "date": today.isoformat(),
         "campaign": "nem-shorts", "kind": "revenue", "status": "pending",
         "amount_vnd": 75000, "evidence_ref": ""},
    ]
    performance_file = _write_demo_csv("perf", store.PERF_COLUMNS, performance)
    ledger_file = _write_demo_csv("ledger", store.LEDGER_COLUMNS, transactions)
    imports = []
    for kind, filename in [("performance", performance_file),
                           ("ledger", ledger_file)]:
        receipt = _run("analytics.import", {
            "dataset": dataset, "kind": kind, "filename": filename,
            "source_kind": "manual", "synthetic": True, "confirm_write": True,
        }, grants=("workspace.write",))
        imports.append(receipt)
        if receipt["status"] != "SUCCEEDED":
            return {"status": "FAILED", "dataset": dataset,
                    "synthetic": True, "imports": imports}
    reports = {}
    for name, skill in REPORT_SKILLS.items():
        input_data = {"dataset": dataset, "campaign": "nem-shorts"}
        receipt = _run(skill, input_data)
        reports[name] = receipt
        if receipt["status"] != "SUCCEEDED":
            return {"status": "FAILED", "dataset": dataset,
                    "synthetic": True, "imports": imports, "reports": reports}
    return {
        "status": "SUCCEEDED", "dataset": dataset, "synthetic": True,
        "imports": imports, "reports": reports,
        "external_data_verified": False, "revenue_verified": False,
        "no_cloud_calls": True, "no_publication": True,
    }


def main():
    parser = argparse.ArgumentParser(description="S3 local-first Intelligence & Analytics")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Create isolated synthetic CSVs and all five reports")
    imp = sub.add_parser("import", help="Import owner-provided CSV under workspace/analytics/inbox")
    imp.add_argument("kind", choices=("performance", "ledger"))
    imp.add_argument("filename")
    imp.add_argument("--dataset", required=True)
    imp.add_argument("--source-kind", choices=sorted(store.SOURCE_KINDS), default="manual")
    imp.add_argument("--confirm-write", action="store_true")
    report = sub.add_parser("report", help="Read-only analytics/finance/experiment report")
    report.add_argument("kind", choices=sorted(REPORT_SKILLS))
    report.add_argument("--dataset", required=True)
    report.add_argument("--campaign")
    sub.add_parser("datasets", help="List datasets without network/model calls")
    args = parser.parse_args()
    if args.command == "demo":
        output = synthetic_demo()
    elif args.command == "datasets":
        output = {"status": "OK", "datasets": store.list_datasets()}
    elif args.command == "import":
        output = _run("analytics.import", {
            "dataset": args.dataset, "kind": args.kind,
            "filename": args.filename, "source_kind": args.source_kind,
            "synthetic": False, "confirm_write": args.confirm_write,
        }, grants=("workspace.write",) if args.confirm_write else ())
    else:
        if args.kind == "experiment" and args.campaign is None:
            parser.error("Experiment requires --campaign for comparable variants")
        payload = {"dataset": args.dataset}
        if args.campaign is not None:
            payload["campaign"] = args.campaign
        output = _run(REPORT_SKILLS[args.kind], payload)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if output["status"] == "FAILED":
        parser.exit(2)
    if output["status"] == "WAITING_APPROVAL":
        parser.exit(3)


if __name__ == "__main__":
    main()
