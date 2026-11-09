"""C7B: owner review of captured first-hand customer interview notes.

This is a local audit layer, NOT identity verification, proof of demand, evidence
registration, network outreach, AI analysis, or permission to execute/spend.
"""

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from agentforge import customer_validation as intake

REVIEW_ACTIONS = frozenset({"RETAINED_FIRSTHAND_CLAIM", "NEEDS_FOLLOWUP", "REJECTED"})
CAPTURE_METADATA = frozenset({
    "captured_at", "consent_confirmed_by_owner", "owner_reviewed",
    "independently_verified", "customer_problem_verified",
    "willingness_to_pay_verified", "evidence_eligible", "evidence_refs",
    "supports", "execution_authorized", "spending_authorized",
})
CAPTURE_FIELDS = intake.DRAFT_FIELDS | CAPTURE_METADATA
REVIEW_FIELDS = frozenset({
    "schema_version", "opportunity_id", "participant_code", "decision",
    "interview_record_sha256", "review_note", "reviewed_at", "owner_reviewed",
    "firsthand_interview_confirmed_by_owner", "quote_context_confirmed_by_owner",
    "consent_confirmed_in_intake", "source_payment_signal", "retained_as_claim",
    "independently_verified", "customer_problem_verified",
    "willingness_to_pay_verified", "payment_verified", "evidence_eligible",
    "evidence_refs", "supports", "execution_authorized", "spending_authorized",
})


def _paths(opportunity_id, participant_code):
    _, record = intake._paths(opportunity_id, participant_code)
    folder = intake.DATA_DIR / "reviews" / opportunity_id
    review = folder / f"{participant_code}.json"
    for path in (intake.DATA_DIR, folder.parent, folder, review):
        if path.is_symlink():
            raise ValueError("Symlinks in interview review storage are forbidden")
    return record, review


def _read_json(path, *, max_bytes):
    if path.is_symlink():
        raise ValueError("Symlinked interview file forbidden")
    if path.stat().st_size > max_bytes:
        raise ValueError("Interview file exceeds size limit")
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(doc, dict):
        raise ValueError("Interview document must be a JSON object")
    return doc, raw


def _load_captured(opportunity_id, participant_code):
    """Validate the immutable C7A record before any owner decision."""
    record_path, review_path = _paths(opportunity_id, participant_code)
    doc, raw = _read_json(record_path, max_bytes=16000)
    if (set(doc) != CAPTURE_FIELDS
            or type(doc.get("schema_version")) is not int
            or doc["schema_version"] != 1
            or doc.get("opportunity_id") != opportunity_id
            or doc.get("participant_code") != participant_code
            or doc.get("status") != "CAPTURED_UNVERIFIED"
            or not isinstance(doc.get("source_channel"), str)
            or doc["source_channel"] not in intake.CHANNELS
            or not isinstance(doc.get("frequency"), str)
            or doc["frequency"] not in intake.FREQUENCIES
            or not isinstance(doc.get("payment_signal"), str)
            or doc["payment_signal"] not in intake.PAYMENT_SIGNALS
            or doc.get("consent_confirmed_by_owner") is not True
            or any(doc.get(k) is not False for k in (
                "owner_reviewed", "independently_verified",
                "customer_problem_verified", "willingness_to_pay_verified",
                "evidence_eligible", "execution_authorized", "spending_authorized"
            ))
            or doc.get("evidence_refs") != []
            or doc.get("supports") != []):
        raise ValueError("Invalid or unauthorized captured interview record")
    try:
        day = date.fromisoformat(doc["interview_date"])
        if day > date.today() or day.isoformat() != doc["interview_date"]:
            raise ValueError("Invalid interview date")
        stamp = datetime.fromisoformat(doc["captured_at"])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Missing captured timestamp timezone")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid interview or capture timestamp") from exc
    for key, min_len, max_len in (
        ("business_context", 12, 300),
        ("problem_quote", 20, 600),
        ("current_workaround", 12, 400),
        ("owner_note", 12, 400),
    ):
        intake._bounded(doc[key], key, min_len, max_len)
    return doc, raw, record_path, review_path


def _load_review(opportunity_id, participant_code):
    captured, raw, record_path, review_path = _load_captured(
        opportunity_id, participant_code
    )
    reviewed, _ = _read_json(review_path, max_bytes=8000)
    action = reviewed.get("decision")
    retained = action == "RETAINED_FIRSTHAND_CLAIM"
    if (set(reviewed) != REVIEW_FIELDS
            or type(reviewed.get("schema_version")) is not int
            or reviewed["schema_version"] != 1
            or reviewed.get("opportunity_id") != opportunity_id
            or reviewed.get("participant_code") != participant_code
            or action not in REVIEW_ACTIONS
            or reviewed.get("interview_record_sha256") != hashlib.sha256(raw).hexdigest()
            or reviewed.get("owner_reviewed") is not True
            or reviewed.get("consent_confirmed_in_intake") is not True
            or reviewed.get("source_payment_signal") != captured["payment_signal"]
            or reviewed.get("retained_as_claim") is not retained
            or reviewed.get("firsthand_interview_confirmed_by_owner") is not retained
            or reviewed.get("quote_context_confirmed_by_owner") is not retained
            or any(reviewed.get(k) is not False for k in (
                "independently_verified", "customer_problem_verified",
                "willingness_to_pay_verified", "payment_verified",
                "evidence_eligible", "execution_authorized", "spending_authorized"
            ))
            or reviewed.get("evidence_refs") != []
            or reviewed.get("supports") != []):
        raise ValueError("Invalid interview review or changed source record")
    intake._bounded(reviewed.get("review_note"), "review_note", 20, 500)
    try:
        stamp = datetime.fromisoformat(reviewed["reviewed_at"])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid review timestamp") from exc
    return reviewed


def inspect(opportunity_id, participant_code):
    """Read local interview metadata; print no customer quote by default."""
    captured, raw, record, review = _load_captured(opportunity_id, participant_code)
    if review.exists():
        reviewed = _load_review(opportunity_id, participant_code)
        decision = reviewed["decision"]
    else:
        decision = "NOT_REVIEWED"
    return {
        "opportunity_id": opportunity_id,
        "participant_code": participant_code,
        "capture_status": "CAPTURED_UNVERIFIED",
        "interview_date": captured["interview_date"],
        "source_channel": captured["source_channel"],
        "payment_signal": captured["payment_signal"],
        "review_status": decision,
        "record_path": str(record),
        "review_path": str(review) if review.exists() else None,
        "record_sha256": hashlib.sha256(raw).hexdigest(),
        "evidence_eligible": False,
    }


def decide(opportunity_id, participant_code, decision, note, *,
           confirm_firsthand_interview=False, confirm_quote_context=False):
    """One immutable owner decision; never updates captured record or registry."""
    if decision not in ("retain", "followup", "reject"):
        raise ValueError("Unknown review decision")
    note = intake._bounded(note, "review_note", 20, 500)
    retained = decision == "retain"
    if retained and (confirm_firsthand_interview is not True
                     or confirm_quote_context is not True):
        raise PermissionError("First-hand interview and quote-context confirmations required")
    if not retained and (confirm_firsthand_interview or confirm_quote_context):
        raise ValueError("Review confirmations only apply to retained first-hand claims")

    captured, raw, _, review = _load_captured(opportunity_id, participant_code)
    result = {
        "schema_version": 1,
        "opportunity_id": opportunity_id,
        "participant_code": participant_code,
        "decision": {
            "retain": "RETAINED_FIRSTHAND_CLAIM",
            "followup": "NEEDS_FOLLOWUP",
            "reject": "REJECTED",
        }[decision],
        "interview_record_sha256": hashlib.sha256(raw).hexdigest(),
        "review_note": note,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "owner_reviewed": True,
        "firsthand_interview_confirmed_by_owner": retained,
        "quote_context_confirmed_by_owner": retained,
        "consent_confirmed_in_intake": True,
        "source_payment_signal": captured["payment_signal"],
        "retained_as_claim": retained,
        "independently_verified": False,
        "customer_problem_verified": False,
        "willingness_to_pay_verified": False,
        "payment_verified": False,
        "evidence_eligible": False,
        "evidence_refs": [],
        "supports": [],
        "execution_authorized": False,
        "spending_authorized": False,
    }
    review.parent.mkdir(parents=True, exist_ok=True)
    with review.open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    return review


def summary(opportunity_id):
    """Fail closed on missing, malformed, or orphaned review records."""
    if not isinstance(opportunity_id, str) or not intake.OPPORTUNITY_RE.fullmatch(opportunity_id):
        raise ValueError("Invalid research opportunity ID")
    folder = intake.DATA_DIR / "records" / opportunity_id
    reviews_dir = intake.DATA_DIR / "reviews" / opportunity_id
    if folder.is_symlink() or reviews_dir.is_symlink():
        raise ValueError("Symlinked customer validation directory")
    counts = {key: 0 for key in sorted(REVIEW_ACTIONS)}
    record_names = set()
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        participant_code = path.stem
        _load_captured(opportunity_id, participant_code)
        record_names.add(participant_code)
        _, review_path = _paths(opportunity_id, participant_code)
        if review_path.exists():
            reviewed = _load_review(opportunity_id, participant_code)
            counts[reviewed["decision"]] += 1
    if reviews_dir.exists():
        for path in reviews_dir.glob("*.json"):
            if path.stem not in record_names:
                raise ValueError("Orphan or unsafe customer interview review")
    total = len(record_names)
    return {
        "opportunity_id": opportunity_id,
        "captured_count": total,
        "unreviewed_count": total - sum(counts.values()),
        "review_counts": counts,
        "customer_problem_verified": False,
        "willingness_to_pay_verified": False,
        "payment_verified": False,
        "evidence_registered": False,
        "execution_authorized": False,
        "spending_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description="C7B local first-hand interview review")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("inspect", "retain", "followup", "reject"):
        cmd = commands.add_parser(action)
        cmd.add_argument("opportunity_id")
        cmd.add_argument("participant_code")
        if action not in ("inspect",):
            cmd.add_argument("--note", required=True)
        if action == "retain":
            cmd.add_argument("--confirm-firsthand-interview", action="store_true")
            cmd.add_argument("--confirm-quote-context", action="store_true")
    cmd = commands.add_parser("summary")
    cmd.add_argument("opportunity_id")
    args = parser.parse_args()
    if args.action == "inspect":
        print(json.dumps(inspect(args.opportunity_id, args.participant_code), ensure_ascii=False, indent=2))
    elif args.action == "summary":
        print(json.dumps(summary(args.opportunity_id), ensure_ascii=False, indent=2))
    else:
        path = decide(
            args.opportunity_id, args.participant_code, args.action, args.note,
            confirm_firsthand_interview=getattr(args, "confirm_firsthand_interview", False),
            confirm_quote_context=getattr(args, "confirm_quote_context", False),
        )
        print("REVIEW SAVED:", path)
        print("CUSTOMER PROBLEM VERIFIED: False")
        print("WILLINGNESS TO PAY VERIFIED: False")
        print("EVIDENCE REGISTERED: False")
        print("EXECUTION AUTHORIZED: False")


if __name__ == "__main__":
    main()
