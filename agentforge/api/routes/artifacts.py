"""Artifact SHA validation and reversible retention mutations."""
from agentforge.core import artifact_acceptance
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path.startswith("/api/artifacts/") and path.endswith("/syntax"):
        parts = path.split("/")
        if (len(parts) != 6 or parts[3] not in {"webapps", "proposals"}
                or set(request) != {"ack", "sha256"} or request["ack"] != "VALIDATE_SYNTAX"):
            raise ValueError("Invalid source validation request")
        namespace, pid = parts[3:5]
        reviewed = "reviewed_webapps" if namespace == "webapps" else "reviewed_proposals"
        if session is None or session.get(reviewed, {}).get(pid) != request["sha256"]:
            raise PermissionError("Inspect exact source before validation")
        from agentforge.ops_control import require_active
        require_active()
        return artifact_acceptance.validate_source(pid, request["sha256"], namespace, db_path=server.task_db_path)
    if path.startswith("/api/artifacts/") and path.endswith("/decision"):
        parts = path.split("/")
        if (len(parts) != 6 or parts[3] not in {"webapps", "proposals"}
                or set(request) != {"ack", "sha256", "expected_revision", "evidence_sha"}):
            raise ValueError("Invalid artifact decision")
        namespace, pid = parts[3:5]
        decision = {"ACCEPT_ARTIFACT": "ACCEPTED", "REJECT_ARTIFACT": "REJECTED"}.get(request["ack"])
        reviewed = "reviewed_webapps" if namespace == "webapps" else "reviewed_proposals"
        if (decision is None or session is None
                or session.get(reviewed, {}).get(pid) != request["sha256"]):
            raise PermissionError("Inspect the exact source before deciding acceptance")
        from agentforge.ops_control import require_active
        require_active()
        return artifact_acceptance.decide(
            pid, request["sha256"], namespace, decision, confirm=True,
            expected_revision=request["expected_revision"], evidence_sha=request["evidence_sha"],
            db_path=server.task_db_path)
    if path == "/api/retention/backup":
        from agentforge.storage import retention
        if (set(request) != {"ack", "kind", "id", "tree_sha"} or
                request.get("ack") != "BACKUP_ARTIFACT"):
            raise PermissionError("Explicit reviewed artifact backup required")
        key = (request["kind"], request["id"])
        if (session is None or session.get("inspected_artifacts", {}).get(key)
                != request["tree_sha"]):
            raise PermissionError("Inspect exact live artifact SHA first")
        return retention.backup(request["kind"], request["id"], request["tree_sha"],
                                confirm=True)
    if path == "/api/retention/quarantine":
        from agentforge.storage import retention
        if (set(request) != {"ack", "backup_id", "tree_sha"} or
                request.get("ack") != "QUARANTINE_ARTIFACT"):
            raise PermissionError("Explicit reversible quarantine required")
        if (session is None or session.get("verified_artifact_backups", {}).get(
                request["backup_id"]) != request["tree_sha"]):
            raise PermissionError("Verify exact backup SHA in this session")
        return retention.quarantine(request["backup_id"], request["tree_sha"],
                                    confirm=True)
    if path == "/api/retention/restore":
        from agentforge.storage import retention
        if (set(request) != {"ack", "backup_id", "tree_sha"} or
                request.get("ack") != "RESTORE_ARTIFACT"):
            raise PermissionError("Explicit owner restore required")
        if (session is None or session.get("verified_artifact_backups", {}).get(
                request["backup_id"]) != request["tree_sha"]):
            raise PermissionError("Verify exact backup SHA in this session")
        return retention.restore(request["backup_id"], request["tree_sha"],
                                 confirm=True)
    return UNHANDLED
