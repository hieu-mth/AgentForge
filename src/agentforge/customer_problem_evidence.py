"""C7C: manually register two corroborating first-hand customer problem claims.

Two owner-attested, distinct interview codes are weak corroboration, NOT
independent fact verification, payment evidence, or permission to act.
Local only: no AI, network, outreach or generated business execution.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge import customer_evidence_review as review
from agentforge import customer_validation as intake
from agentforge.evaluation import OPPORTUNITIES
from agentforge.evidence_registry import valid_references_for_opportunity

SOURCE_TYPE = "TWO_OWNER_REVIEWED_CUSTOMER_CLAIMS"
SCOPE = "customer_problem"


def _read_sources(opportunity_id, participants):
    if not isinstance(opportunity_id, str) or not intake.OPPORTUNITY_RE.fullmatch(opportunity_id):
        raise ValueError("Invalid opportunity ID")
    if not isinstance(participants, (list, tuple)) or len(participants) != 2:
        raise ValueError("Exactly two participants are required")
    if any(not isinstance(code, str) or not intake.PARTICIPANT_RE.fullmatch(code)
           for code in participants):
        raise ValueError("Invalid participant code")
    if participants[0] == participants[1]:
        raise ValueError("Two distinct participant codes are required")
    inspected = []
    for code in sorted(participants):
        captured, raw, record_path, review_path = review._load_captured(opportunity_id, code)
        decision = review._load_review(opportunity_id, code)
        if (decision["decision"] != "RETAINED_FIRSTHAND_CLAIM"
                or decision["retained_as_claim"] is not True
                or decision["firsthand_interview_confirmed_by_owner"] is not True
                or decision["quote_context_confirmed_by_owner"] is not True
                or decision["consent_confirmed_in_intake"] is not True
                or captured["consent_confirmed_by_owner"] is not True):
            raise ValueError("Only retained, consented real interview claims qualify")
        # _load_review already verified the record fingerprint and review flags.
        if review_path.is_symlink():
            raise ValueError("Review cannot be a symlink")
        decision_raw = review_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != decision["interview_record_sha256"]:
            raise ValueError("Source interview changed during review")
        inspected.append({
            "participant_code": code,
            "record_sha256": hashlib.sha256(raw).hexdigest(),
            "review_sha256": hashlib.sha256(decision_raw).hexdigest(),
            "interview_date": captured["interview_date"],
            "source_channel": captured["source_channel"],
        })
    return inspected


def inspect(opportunity_id):
    """Summary of reviewable interviews, without exposing customer quotes."""
    result = review.summary(opportunity_id)  # also rejects orphan/tampered reviews
    folder = intake.DATA_DIR / "records" / opportunity_id
    retained = []
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            code = path.stem
            _, review_path = review._paths(opportunity_id, code)
            if review_path.is_file():
                decision = review._load_review(opportunity_id, code)
                if decision["decision"] == "RETAINED_FIRSTHAND_CLAIM":
                    retained.append(code)
    return {
        "opportunity_id": opportunity_id,
        "captured_count": result["captured_count"],
        "retained_count": len(retained),
        "retained_participants": retained,
        "minimum_distinct_retained_interviews": 2,
        "ready_for_owner_corroboration": len(retained) >= 2,
        "independently_verified": False,
        "willingness_to_pay_verified": False,
        "payment_verified": False,
        "execution_authorized": False,
        "spending_authorized": False,
    }


def register(opportunity_id, participants, note, *,
             confirm_independent_interviews=False, confirm_same_problem=False,
             opportunities_dir=None):
    """Register customer_problem scope only, after two explicit owner attestations.

    These are owner-attested first-hand accounts, NOT independently verified facts.
    """
    if confirm_independent_interviews is not True or confirm_same_problem is not True:
        raise PermissionError("Two explicit owner confirmations are required")
    note = intake._bounded(note, "corroboration_note", 30, 500)
    sources = _read_sources(opportunity_id, participants)
    base = Path(opportunities_dir) if opportunities_dir is not None else OPPORTUNITIES
    evidence_dir = base / "evidence"
    index_path = base / "evidence_index.json"
    lock_path = base / ".evidence_index.lock"
    identity = json.dumps([opportunity_id, sorted(participants)], separators=(",", ":"))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    reference = f"owner-reviewed:customer-{digest}"
    filename = f"customer-problem-{digest}.json"
    evidence_path = evidence_dir / filename
    for p in (base, evidence_dir, index_path, lock_path, evidence_path):
        if p.is_symlink():
            raise ValueError("Symlinks in evidence storage are forbidden")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with lock_path.open("x", encoding="utf-8") as lock:
        lock.write("C7C customer problem registration in progress\n")
    written = False
    temp_path = None
    try:
        if evidence_path.exists():
            raise FileExistsError("Customer problem pair already registered")
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
        else:
            index = {"records": {}}
        if not isinstance(index, dict) or not isinstance(index.get("records"), dict):
            raise ValueError("Invalid evidence index")
        if reference in index["records"]:
            raise FileExistsError("Customer problem reference already registered")

        # Fail closed if an interview or owner review changed between reading and writing.
        if _read_sources(opportunity_id, participants) != sources:
            raise ValueError("Interview or review changed during registration")
        now = datetime.now(timezone.utc).isoformat()
        artifact = {
            "reference": reference,
            "source_type": SOURCE_TYPE,
            "opportunity_id": opportunity_id,
            "scope": SCOPE,
            "participants": sources,
            "corroboration_note": note,
            "two_independent_interviews_attested_by_owner": True,
            "same_problem_attested_by_owner": True,
            "owner_reviewed": True,
            "evidence_level": "TWO_FIRSTHAND_CLAIMS_NOT_INDEPENDENTLY_VERIFIED",
            "independently_verified": False,
            "customer_demand_verified": False,
            "willingness_to_pay_verified": False,
            "payment_verified": False,
            "registered_at": now,
            "execution_authorized": False,
            "spending_authorized": False,
        }
        entry = {
            "owner_reviewed": True,
            "supports": [SCOPE],
            "source_type": SOURCE_TYPE,
            "source_file": filename,
            "opportunity_id": opportunity_id,
            "registered_at": now,
        }
        with evidence_path.open("x", encoding="utf-8") as file:
            written = True
            json.dump(artifact, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        index["records"][reference] = entry
        if not valid_references_for_opportunity(
            [reference], SCOPE, index, evidence_dir, opportunity_id
        ):
            raise ValueError("Customer problem registry validation failed")
        temp_path = base / f".evidence_index.{uuid4().hex}.tmp"
        with temp_path.open("x", encoding="utf-8") as file:
            json.dump(index, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, index_path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        if written:
            evidence_path.unlink(missing_ok=True)
        raise
    finally:
        lock_path.unlink(missing_ok=True)
    return {
        "reference": reference,
        "scope": SCOPE,
        "source_file": str(evidence_path),
        "index_file": str(index_path),
        "independently_verified": False,
        "willingness_to_pay_verified": False,
        "payment_verified": False,
        "execution_authorized": False,
        "spending_authorized": False,
    }


def validate_registered_artifact(reference, entry, evidence_path):
    """Verify a customer-problem reference against original captured/reviewed files.

    Used by the registry on every Evaluation read. This detects accidental
    mutations; local file hashes are not cryptographic proof of authenticity.
    """
    try:
        if (not isinstance(reference, str)
                or not reference.startswith("owner-reviewed:customer-")
                or not isinstance(entry, dict)
                or entry.get("source_type") != SOURCE_TYPE
                or entry.get("supports") != [SCOPE]
                or entry.get("owner_reviewed") is not True):
            return False
        path = Path(evidence_path)
        if path.is_symlink() or path.stat().st_size > 16000:
            return False
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(artifact, dict):
            return False
        opportunity_id = entry.get("opportunity_id")
        rows = artifact.get("participants")
        if (not isinstance(opportunity_id, str)
                or not intake.OPPORTUNITY_RE.fullmatch(opportunity_id)
                or not isinstance(rows, list) or len(rows) != 2
                or not all(isinstance(row, dict) for row in rows)):
            return False
        participants = [row.get("participant_code") for row in rows]
        if (any(not isinstance(x, str) for x in participants)
                or len(set(participants)) != 2):
            return False
        identity = json.dumps([opportunity_id, sorted(participants)], separators=(",", ":"))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        expected_ref = f"owner-reviewed:customer-{digest}"
        if (reference != expected_ref
                or path.name != f"customer-problem-{digest}.json"
                or entry.get("source_file") != path.name
                or artifact.get("reference") != reference
                or artifact.get("source_type") != SOURCE_TYPE
                or artifact.get("opportunity_id") != opportunity_id
                or artifact.get("scope") != SCOPE
                or artifact.get("owner_reviewed") is not True
                or artifact.get("two_independent_interviews_attested_by_owner") is not True
                or artifact.get("same_problem_attested_by_owner") is not True
                or artifact.get("evidence_level") != "TWO_FIRSTHAND_CLAIMS_NOT_INDEPENDENTLY_VERIFIED"
                or any(artifact.get(key) is not False for key in (
                    "independently_verified", "customer_demand_verified",
                    "willingness_to_pay_verified", "payment_verified",
                    "execution_authorized", "spending_authorized",
                ))):
            return False
        intake._bounded(artifact.get("corroboration_note"), "corroboration_note", 30, 500)
        return rows == _read_sources(opportunity_id, participants)
    except (OSError, TypeError, ValueError, KeyError, UnicodeError):
        return False


def main():
    parser = argparse.ArgumentParser(description="C7C owner-attested customer problem corroboration")
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("inspect", help="Show local retained interviews without quotes")
    p.add_argument("opportunity_id")
    p = commands.add_parser("register", help="Register two confirmed first-hand claims")
    p.add_argument("opportunity_id")
    p.add_argument("participant_a")
    p.add_argument("participant_b")
    p.add_argument("--note", required=True)
    p.add_argument("--confirm-independent-interviews", action="store_true")
    p.add_argument("--confirm-same-problem", action="store_true")
    args = parser.parse_args()
    if args.action == "inspect":
        result = inspect(args.opportunity_id)
    else:
        result = register(
            args.opportunity_id, [args.participant_a, args.participant_b], args.note,
            confirm_independent_interviews=args.confirm_independent_interviews,
            confirm_same_problem=args.confirm_same_problem,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
