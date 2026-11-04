import re
from pathlib import Path


REF_PATTERN = re.compile(
    r"owner-reviewed:[a-z0-9][a-z0-9_-]{0,63}\Z"
)

FILE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9_-]{0,80}\.(?:txt|md|json)\Z"
)


def valid_references(refs, scope, registry, evidence_dir):
    """Validate local evidence references. Not a factual truth check."""
    if not isinstance(refs, list) or not refs:
        return False

    if not isinstance(registry, dict):
        return False

    records = registry.get("records")

    if not isinstance(records, dict):
        return False

    root = Path(evidence_dir).resolve()

    for ref in refs:
        if not isinstance(ref, str) or not REF_PATTERN.fullmatch(ref):
            return False

        record = records.get(ref)

        if not isinstance(record, dict):
            return False

        if record.get("owner_reviewed") is not True:
            return False

        supports = record.get("supports")

        if not isinstance(supports, list) or scope not in supports:
            return False

        filename = record.get("source_file")

        if not isinstance(filename, str) or not FILE_PATTERN.fullmatch(filename):
            return False

        path = root / filename

        try:
            if path.is_symlink() or not path.is_file():
                return False

            if not path.resolve().is_relative_to(root):
                return False

            if path.stat().st_size == 0:
                return False
        except OSError:
            return False

        # C7C: customer-problem references must still match the captured interview
        # and owner-review fingerprints at the time of evaluation.
        if (record.get("source_type") == "TWO_OWNER_REVIEWED_CUSTOMER_CLAIMS"
                or re.fullmatch(r"owner-reviewed:customer-[0-9a-f]{32}", ref) is not None):
            from agentforge.customer_problem_evidence import validate_registered_artifact
            if not validate_registered_artifact(ref, record, path):
                return False

    return True


def valid_references_for_opportunity(refs, scope, registry, evidence_dir, opportunity_id):
    """Require both local evidence integrity and the matching opportunity ID."""
    if not isinstance(opportunity_id, str) or not opportunity_id.strip():
        return False
    if not valid_references(refs, scope, registry, evidence_dir):
        return False
    return all(
        registry["records"][ref].get("opportunity_id") == opportunity_id
        for ref in refs
    )
