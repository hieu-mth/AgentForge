"""C7A: local intake for first-hand customer interviews.

No model calls, network access, outreach, registration in the evidence index,
or execution/spending authority. Captured notes are NOT independently verified.
"""

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from agentforge.paths import REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT
DATA_DIR = ROOT / "data" / "company" / "customer_validation"
OPPORTUNITY_RE = re.compile(r"research-[a-f0-9]{8}\Z")
PARTICIPANT_RE = re.compile(r"[a-z][a-z0-9_-]{2,31}\Z")
CHANNELS = frozenset({"IN_PERSON", "CALL", "CHAT"})
FREQUENCIES = frozenset({"DAILY", "WEEKLY", "MONTHLY", "RARE", "UNKNOWN"})
PAYMENT_SIGNALS = frozenset({
    "NOT_DISCUSSED", "VERBAL_INTEREST", "DECLINED", "PAST_PAYMENT_CLAIM",
})
DRAFT_FIELDS = frozenset({
    "schema_version", "opportunity_id", "participant_code", "status",
    "interview_date", "source_channel", "business_context", "problem_quote",
    "current_workaround", "frequency", "payment_signal", "owner_note",
})

QUESTIONS = (
    "1. Kể về lần gần nhất bạn phải tổng hợp đơn hàng, phí sàn hoặc lợi nhuận thủ công?",
    "2. Khi đó bạn đang làm bằng công cụ nào, từng bước ra sao?",
    "3. Việc này xảy ra bao lâu một lần? Tốn bao nhiêu thời gian hoặc gây lỗi gì?",
    "4. Bạn từng trả tiền cho cách giải quyết nào chưa? (Không yêu cầu chia sẻ hóa đơn có PII.)",
    "5. Nếu được cải thiện một bước trong quy trình, bạn muốn cải thiện điều gì trước?",
)


def _validate_ids(opportunity_id, participant_code):
    if not isinstance(opportunity_id, str) or not OPPORTUNITY_RE.fullmatch(opportunity_id):
        raise ValueError("Invalid research opportunity ID")
    if not isinstance(participant_code, str) or not PARTICIPANT_RE.fullmatch(participant_code):
        raise ValueError("Use a pseudonymous participant code such as shop_01")


def _paths(opportunity_id, participant_code):
    _validate_ids(opportunity_id, participant_code)
    draft = DATA_DIR / "drafts" / opportunity_id / f"{participant_code}.json"
    record = DATA_DIR / "records" / opportunity_id / f"{participant_code}.json"
    for path in (DATA_DIR, draft.parent.parent, draft.parent, record.parent.parent, record.parent, draft, record):
        if path.is_symlink():
            raise ValueError("Symlinks in customer interview storage are forbidden")
    return draft, record


def new_draft(opportunity_id, participant_code):
    draft, record = _paths(opportunity_id, participant_code)
    if record.exists():
        raise FileExistsError("An interview for this participant already exists")
    draft.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "opportunity_id": opportunity_id,
        "participant_code": participant_code,
        "status": "DRAFT",
        "interview_date": "",
        "source_channel": "",
        "business_context": "",
        "problem_quote": "",
        "current_workaround": "",
        "frequency": "UNKNOWN",
        "payment_signal": "NOT_DISCUSSED",
        "owner_note": "",
    }
    with draft.open("x", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
    return draft


def _bounded(value, name, minimum, maximum):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f"{name} must be {minimum}-{maximum} characters")
    # These fields describe anonymous business context; they do not need URLs/emails.
    if "@" in value or "http://" in value.lower() or "https://" in value.lower():
        raise ValueError(f"{name} must not include email or web links")
    return value.strip()


def _read_draft(opportunity_id, participant_code):
    draft, record = _paths(opportunity_id, participant_code)
    if draft.stat().st_size > 12_000:
        raise ValueError("Interview draft is too large")
    doc = json.loads(draft.read_text(encoding="utf-8-sig"))
    if not isinstance(doc, dict) or set(doc) != DRAFT_FIELDS:
        raise ValueError("Unexpected interview fields")
    if (type(doc["schema_version"]) is not int or doc["schema_version"] != 1
            or doc["opportunity_id"] != opportunity_id
            or doc["participant_code"] != participant_code
            or doc["status"] != "DRAFT"):
        raise ValueError("Draft identity, version or status mismatch")
    if (not isinstance(doc["interview_date"], str)
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", doc["interview_date"])):
        raise ValueError("interview_date must be YYYY-MM-DD")
    try:
        observed = date.fromisoformat(doc["interview_date"])
    except (ValueError, TypeError):
        raise ValueError("interview_date must be YYYY-MM-DD") from None
    if observed > date.today():
        raise ValueError("Interview date cannot be in the future")
    if not isinstance(doc["source_channel"], str) or doc["source_channel"] not in CHANNELS:
        raise ValueError("Invalid source_channel")
    if not isinstance(doc["frequency"], str) or doc["frequency"] not in FREQUENCIES:
        raise ValueError("Invalid frequency")
    if not isinstance(doc["payment_signal"], str) or doc["payment_signal"] not in PAYMENT_SIGNALS:
        raise ValueError("Invalid payment_signal")
    for key, bounds in {
        "business_context": (12, 300),
        "problem_quote": (20, 600),
        "current_workaround": (12, 400),
        "owner_note": (12, 400),
    }.items():
        doc[key] = _bounded(doc[key], key, *bounds)
    return doc, draft, record


def check_draft(opportunity_id, participant_code):
    """Validate only; never write and never classify this as business proof."""
    doc, _, _ = _read_draft(opportunity_id, participant_code)
    return {"status": "READY_TO_CAPTURE", "participant_code": doc["participant_code"]}


def capture(opportunity_id, participant_code, *, confirm_consent=False):
    """Save an immutable interview note, never evidence for Evaluation."""
    if confirm_consent is not True:
        raise PermissionError("Explicit --confirm-consent required before storing quotes")
    doc, _, record = _read_draft(opportunity_id, participant_code)
    record.parent.mkdir(parents=True, exist_ok=True)
    archived = {
        **doc,
        "status": "CAPTURED_UNVERIFIED",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "consent_confirmed_by_owner": True,
        "owner_reviewed": False,
        "independently_verified": False,
        "customer_problem_verified": False,
        "willingness_to_pay_verified": False,
        "evidence_eligible": False,
        "evidence_refs": [],
        "supports": [],
        "execution_authorized": False,
        "spending_authorized": False,
    }
    with record.open("x", encoding="utf-8") as output:
        json.dump(archived, output, ensure_ascii=False, indent=2)
    return record


def summary(opportunity_id):
    if not isinstance(opportunity_id, str) or not OPPORTUNITY_RE.fullmatch(opportunity_id):
        raise ValueError("Invalid research opportunity ID")
    folder = DATA_DIR / "records" / opportunity_id
    if folder.is_symlink():
        raise ValueError("Symlinked interview folder forbidden")
    records = list(folder.glob("*.json")) if folder.exists() else []
    counts = {key: 0 for key in sorted(PAYMENT_SIGNALS)}
    for path in records:
        participant = path.stem
        _, expected = _paths(opportunity_id, participant)
        if path != expected:
            raise ValueError("Unexpected interview record path")
        doc = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(doc, dict)
                or doc.get("opportunity_id") != opportunity_id
                or doc.get("participant_code") != participant
                or doc.get("status") != "CAPTURED_UNVERIFIED"
                or not isinstance(doc.get("payment_signal"), str)
                or doc["payment_signal"] not in PAYMENT_SIGNALS
                or doc.get("execution_authorized") is not False
                or doc.get("spending_authorized") is not False
                or doc.get("evidence_eligible") is not False
                or doc.get("supports") != []):
            raise ValueError(f"Invalid customer interview: {path.name}")
        counts[doc["payment_signal"]] += 1
    return {
        "opportunity_id": opportunity_id,
        "interview_count": len(records),
        "payment_signal_counts": counts,
        "customer_demand_verified": False,
        "willingness_to_pay_verified": False,
        "evidence_registered": False,
        "execution_authorized": False,
        "spending_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description="C7A local-only customer interview intake")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("questions", help="Show neutral interview prompts; no outreach")
    for name in ("new", "check", "capture"):
        command = commands.add_parser(name)
        command.add_argument("opportunity_id")
        command.add_argument("participant_code")
        if name == "capture":
            command.add_argument("--confirm-consent", action="store_true")
    s = commands.add_parser("summary")
    s.add_argument("opportunity_id")
    args = parser.parse_args()
    if args.action == "questions":
        print("INTERVIEW GUIDE: ask neutrally; do not infer completed purchases")
        for item in QUESTIONS:
            print(item)
        return
    if args.action == "new":
        print("DRAFT:", new_draft(args.opportunity_id, args.participant_code))
    elif args.action == "check":
        print(json.dumps(check_draft(args.opportunity_id, args.participant_code)))
    elif args.action == "capture":
        print("CAPTURED:", capture(args.opportunity_id, args.participant_code,
                                     confirm_consent=args.confirm_consent))
        print("EVIDENCE REGISTERED: False")
        print("EXECUTION AUTHORIZED: False")
    else:
        print(json.dumps(summary(args.opportunity_id), indent=2))


if __name__ == "__main__":
    main()
