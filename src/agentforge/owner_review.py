"""Explicit local decisions for evidence candidates; does not register evidence."""

import argparse
import json
import re
from datetime import datetime, timezone

from agentforge import task_inbox
from agentforge.evaluation import REQUIRED
from agentforge.source_review import FIELDS

CANDIDATE_RE = re.compile(r"C[1-9][0-9]{0,3}\Z")
# Quote-matched page text is not sufficient for willingness-to-pay or KILL.
REVIEWABLE_SCOPES = frozenset(REQUIRED) - {"willingness_to_pay"}

# Page quotes alone do not establish customer demand, payments or unit economics.
# Preserve the existing paid-alternative/differentiation handoff while limiting
# quote-only registrations to these narrow, owner-reviewed scopes.
QUOTE_SCOPE_BY_FIELD = {
    "paid_alternative": frozenset({"differentiation"}),
    "acquisition_channel": frozenset({"distribution"}),
}

# Catalog entries are market intelligence, never evaluation evidence.
MARKET_CLASS_BY_FIELD = {
    "price": "ADVERTISED_PRICE",
    "customer_pain": "VENDOR_CLAIM",
    "paid_alternative": "VENDOR_CLAIM",
    "acquisition_channel": "VENDOR_CLAIM",
    "other": "VENDOR_CLAIM",
}


def load_candidates(task_id):
    task = task_inbox.read_task(task_id)
    if task.get("status") != "PROPOSED":
        raise ValueError("Task is not proposed")
    path = task_inbox.DATA_DIR / "evidence_candidates" / f"{task_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("task_id") != task_id
        or document.get("opportunity_id") != task.get("opportunity_id")
        or document.get("status") != "PENDING_OWNER_REVIEW"
        or document.get("owner_reviewed") is not False
        or document.get("execution_authorized") is not False
        or document.get("spending_authorized") is not False
        or document.get("source_review_file") != f"reviews/{task_id}.json"
        or not isinstance(document.get("candidates"), list)
    ):
        raise ValueError("Invalid candidate handoff")
    ids = []
    for item in document["candidates"]:
        if not isinstance(item, dict) or not isinstance(item.get("candidate_id"), str):
            raise ValueError("Invalid candidate")
        ids.append(item["candidate_id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate candidate IDs")
    return document


def decide(task_id, candidate_id, decision, note, *, scope=None, confirm=False, classification=None):
    if not isinstance(candidate_id, str) or not CANDIDATE_RE.fullmatch(candidate_id):
        raise ValueError("Invalid candidate ID")
    if decision not in ("approve", "reject", "catalog"):
        raise ValueError("Unknown decision")
    if not isinstance(note, str) or len(note.strip()) < 12:
        raise ValueError("A meaningful review note (12+ characters) is required")
    if decision == "approve":
        if confirm is not True:
            raise PermissionError("Explicit manual source review confirmation required")
        if scope not in REVIEWABLE_SCOPES:
            raise ValueError("Scope not eligible for quote-only evidence")
        if classification is not None:
            raise ValueError("Approval cannot set market classification")
    elif decision == "catalog":
        if confirm is not True:
            raise PermissionError("Explicit owner review confirmation required")
        if scope is not None:
            raise ValueError("Market intelligence must not support evaluation scopes")
        if classification not in ("VENDOR_CLAIM", "ADVERTISED_PRICE"):
            raise ValueError("Invalid market intelligence classification")
    elif scope is not None or classification is not None:
        raise ValueError("Rejected candidates must not have a scope or classification")

    document = load_candidates(task_id)
    selected = [x for x in document["candidates"] if x["candidate_id"] == candidate_id]
    if len(selected) != 1:
        raise ValueError("Candidate not found")
    item = selected[0]
    if decision == "approve" and scope not in QUOTE_SCOPE_BY_FIELD.get(item.get("field"), ()):
        raise ValueError("Quote-only source field cannot support this evaluation scope")
    if decision == "catalog" and classification != MARKET_CLASS_BY_FIELD.get(item.get("field")):
        raise ValueError("Market classification does not match the quoted field")
    if (
        item.get("quote_status") != "MATCHED_IN_PAGE"
        or item.get("independently_verified") is not False
        or item.get("owner_reviewed") is not False
        or item.get("supports") != []
        or item.get("field") not in FIELDS
        or item.get("source_url") not in task_inbox.read_task(task_id).get("source_urls", [])
        or not isinstance(item.get("statement"), str)
        or not item["statement"].strip()
        or not isinstance(item.get("quote"), str)
        or not 30 <= len(item["quote"].strip()) <= 300
    ):
        raise ValueError("Invalid evidence candidate")

    report_path = task_inbox.DATA_DIR / "reviews" / f"{task_id}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(report, dict)
        or report.get("task_id") != task_id
        or report.get("opportunity_id") != document["opportunity_id"]
        or report.get("review_status") != "QUOTE_REVIEW_ONLY"
        or not isinstance(report.get("source_reviews"), list)
        or report.get("execution_authorized") is not False
        or report.get("spending_authorized") is not False
    ):
        raise ValueError("Invalid source review")

    def same_observation(review):
        if not isinstance(review, dict):
            return False
        if (review.get("url") != item["source_url"]
                or review.get("status") != "QUOTES_CHECKED_NOT_FACT_CHECKED"):
            return False
        observations = review.get("observations", [])
        return isinstance(observations, list) and any(
            isinstance(obs, dict)
            and obs.get("field") == item["field"]
            and obs.get("statement") == item["statement"]
            and obs.get("quote") == item["quote"]
            and obs.get("quote_status") == "MATCHED_IN_PAGE"
            and obs.get("independently_verified") is False
            for obs in observations
        )

    if not any(same_observation(review) for review in report["source_reviews"]):
        raise ValueError("Candidate does not match source review")

    output = task_inbox.DATA_DIR / "owner_decisions" / task_id / f"{candidate_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "decision": (
            "APPROVED_FOR_REGISTRATION" if decision == "approve"
            else "CATALOGUED_MARKET_INTELLIGENCE" if decision == "catalog"
            else "REJECTED"
        ),
        "scope": scope if decision == "approve" else None,
        "source_url": item["source_url"],
        "quote": item["quote"],
        "review_note": note.strip()[:500],
        "manual_review_confirmed": confirm is True if decision in ("approve", "catalog") else False,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "registered": False,
        "execution_authorized": False,
        "spending_authorized": False,
    }
    if decision == "catalog":
        # A single owner decision file is the catalog record. It is NOT inserted
        # into the evidence index, and cannot be registered as business proof.
        result.update({
            "opportunity_id": document["opportunity_id"],
            "classification": classification,
            "field": item["field"],
            "statement": item["statement"],
            "quote_status": item["quote_status"],
            "owner_reviewed": True,
            "independently_verified": False,
            "evidence_eligible": False,
            "supports": [],
            "customer_demand_verified": False,
            "revenue_verified": False,
        })
    with output.open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    return output


def main():
    parser = argparse.ArgumentParser(description="Manual evidence candidate decisions")
    commands = parser.add_subparsers(dest="action", required=True)
    show = commands.add_parser("show")
    show.add_argument("task_id")
    for action in ("approve", "reject", "catalog"):
        command = commands.add_parser(action)
        command.add_argument("task_id")
        command.add_argument("candidate_id")
        command.add_argument("--note", required=True)
        if action == "approve":
            command.add_argument("--scope", required=True, choices=sorted(REVIEWABLE_SCOPES))
            command.add_argument("--confirm-manual-review", action="store_true")
        elif action == "catalog":
            command.add_argument(
                "--classification", required=True,
                choices=("ADVERTISED_PRICE", "VENDOR_CLAIM"),
            )
            command.add_argument("--confirm-manual-review", action="store_true")
    args = parser.parse_args()
    if args.action == "show":
        print(json.dumps(load_candidates(args.task_id), ensure_ascii=False, indent=2))
    else:
        output = decide(
            args.task_id, args.candidate_id, args.action, args.note,
            scope=getattr(args, "scope", None),
            confirm=getattr(args, "confirm_manual_review", False),
            classification=getattr(args, "classification", None),
        )
        print("DECISION SAVED:", output)
        print("EVIDENCE REGISTERED: False")
        print("EXECUTION AUTHORIZED: False")


if __name__ == "__main__":
    main()
