"""Register manually reviewed source quotes in the local evidence index.

Registration records provenance, not independent truth or permission to act.
The original owner decision is deliberately kept immutable.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge import owner_review, task_inbox
from agentforge.evaluation import OPPORTUNITIES
from agentforge.evidence_registry import valid_references


def register_evidence(task_id, candidate_id, *, opportunities_dir=None):
    if (
        not isinstance(candidate_id, str)
        or not owner_review.CANDIDATE_RE.fullmatch(candidate_id)
    ):
        raise ValueError("Invalid candidate ID")

    task = task_inbox.read_task(task_id)
    if task.get("status") != "PROPOSED":
        raise ValueError("Task must remain proposed")

    handoff = owner_review.load_candidates(task_id)
    matching = [
        item for item in handoff["candidates"]
        if item["candidate_id"] == candidate_id
    ]
    if len(matching) != 1:
        raise ValueError("Candidate not found")
    candidate = matching[0]

    decision_path = (
        task_inbox.DATA_DIR / "owner_decisions" / task_id / f"{candidate_id}.json"
    )
    if decision_path.is_symlink():
        raise ValueError("Decision file cannot be a symlink")
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    scope = decision.get("scope") if isinstance(decision, dict) else None

    if (
        not isinstance(decision, dict)
        or decision.get("task_id") != task_id
        or decision.get("candidate_id") != candidate_id
        or decision.get("decision") != "APPROVED_FOR_REGISTRATION"
        or decision.get("manual_review_confirmed") is not True
        or decision.get("registered") is not False
        or decision.get("execution_authorized") is not False
        or decision.get("spending_authorized") is not False
        or scope not in owner_review.REVIEWABLE_SCOPES
        or scope not in owner_review.QUOTE_SCOPE_BY_FIELD.get(candidate.get("field"), ())
        or decision.get("source_url") != candidate.get("source_url")
        or decision.get("quote") != candidate.get("quote")
        or not isinstance(decision.get("review_note"), str)
        or len(decision["review_note"].strip()) < 12
        or not isinstance(decision.get("decided_at"), str)
        or not decision["decided_at"].strip()
        or candidate.get("quote_status") != "MATCHED_IN_PAGE"
        or candidate.get("independently_verified") is not False
        or candidate.get("owner_reviewed") is not False
        or candidate.get("supports") != []
        or candidate.get("source_url") not in task.get("source_urls", [])
        or not isinstance(candidate.get("field"), str)
        or not isinstance(candidate.get("statement"), str)
        or not candidate["statement"].strip()
    ):
        raise ValueError("Decision or candidate is not eligible for registration")

    # Recheck source-review provenance. A quote match is not a factual verification.
    report_path = task_inbox.DATA_DIR / "reviews" / f"{task_id}.json"
    if report_path.is_symlink():
        raise ValueError("Source review file cannot be a symlink")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(report, dict)
        or report.get("task_id") != task_id
        or report.get("opportunity_id") != handoff.get("opportunity_id")
        or report.get("review_status") != "QUOTE_REVIEW_ONLY"
        or report.get("customer_demand_verified") is not False
        or report.get("revenue_verified") is not False
        or report.get("execution_authorized") is not False
        or report.get("spending_authorized") is not False
        or not isinstance(report.get("source_reviews"), list)
    ):
        raise ValueError("Invalid source review provenance")

    def matches_source(review):
        if (
            not isinstance(review, dict)
            or review.get("url") != candidate["source_url"]
            or review.get("status") != "QUOTES_CHECKED_NOT_FACT_CHECKED"
            or not isinstance(review.get("observations"), list)
        ):
            return False
        return any(
            isinstance(obs, dict)
            and obs.get("field") == candidate["field"]
            and obs.get("statement") == candidate["statement"]
            and obs.get("quote") == candidate["quote"]
            and obs.get("quote_status") == "MATCHED_IN_PAGE"
            and obs.get("independently_verified") is False
            for obs in review["observations"]
        )

    if sum(matches_source(review) for review in report["source_reviews"]) != 1:
        raise ValueError("Candidate no longer matches the source review")

    base = Path(opportunities_dir) if opportunities_dir is not None else OPPORTUNITIES
    evidence_dir = base / "evidence"
    index_path = base / "evidence_index.json"
    lock_path = base / ".evidence_index.lock"
    digest = hashlib.sha256(f"{task_id}:{candidate_id}".encode()).hexdigest()[:32]
    reference = f"owner-reviewed:{digest}"
    filename = f"source-quote-{digest}.json"
    evidence_path = evidence_dir / filename

    if base.is_symlink() or evidence_dir.is_symlink() or index_path.is_symlink():
        raise ValueError("Evidence storage cannot use symlinks")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Cooperating local CLI processes cannot update the index concurrently.
    # A stale lock requires manual inspection before removal.
    with lock_path.open("x", encoding="utf-8") as lock:
        lock.write("Evidence registration in progress\n")

    evidence_written = False
    index_temp = None
    try:
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
        else:
            index = {"records": {}}
        if not isinstance(index, dict) or not isinstance(index.get("records"), dict):
            raise ValueError("Invalid evidence index")
        if reference in index["records"] or evidence_path.exists():
            raise FileExistsError("Evidence already registered; no overwrite")

        registered_at = datetime.now(timezone.utc).isoformat()
        artifact = {
            "reference": reference,
            "source_type": "OWNER_REVIEWED_SOURCE_QUOTE",
            "task_id": task_id,
            "candidate_id": candidate_id,
            "opportunity_id": handoff["opportunity_id"],
            "source_url": candidate["source_url"],
            "field": candidate["field"],
            "statement": candidate["statement"],
            "quote": candidate["quote"],
            "quote_status": "MATCHED_IN_PAGE",
            "independently_verified": False,
            "owner_reviewed": True,
            "manual_review_confirmed": True,
            "review_note": decision["review_note"],
            "scope": scope,
            "decided_at": decision["decided_at"],
            "registered_at": registered_at,
            "execution_authorized": False,
            "spending_authorized": False,
        }
        entry = {
            "owner_reviewed": True,
            "supports": [scope],
            "source_file": filename,
            "opportunity_id": handoff["opportunity_id"],
            "source_url": candidate["source_url"],
            "source_type": "OWNER_REVIEWED_SOURCE_QUOTE",
            "registered_at": registered_at,
        }

        with evidence_path.open("x", encoding="utf-8") as file:
            evidence_written = True
            json.dump(artifact, file, ensure_ascii=False, indent=2)

        index["records"][reference] = entry
        if not valid_references([reference], scope, index, evidence_dir):
            raise ValueError("Registered evidence does not pass registry validation")

        index_temp = base / f".evidence_index.{uuid4().hex}.tmp"
        with index_temp.open("x", encoding="utf-8") as file:
            json.dump(index, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(index_temp, index_path)
    except Exception:
        if index_temp is not None:
            index_temp.unlink(missing_ok=True)
        if evidence_written:
            evidence_path.unlink(missing_ok=True)
        raise
    finally:
        lock_path.unlink(missing_ok=True)

    return {
        "reference": reference,
        "source_file": str(evidence_path),
        "index_file": str(index_path),
        "scope": scope,
        "execution_authorized": False,
        "spending_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Register owner-reviewed evidence locally")
    parser.add_argument("task_id")
    parser.add_argument("candidate_id")
    args = parser.parse_args()
    result = register_evidence(args.task_id, args.candidate_id)
    print("EVIDENCE REFERENCE:", result["reference"])
    print("SCOPE:", result["scope"])
    print("INDEX:", result["index_file"])
    print("EXECUTION AUTHORIZED: False")
    print("SPENDING AUTHORIZED: False")


if __name__ == "__main__":
    main()
