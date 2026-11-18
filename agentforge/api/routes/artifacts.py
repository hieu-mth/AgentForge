"""Artifact SHA validation and reversible retention mutations."""
from agentforge.core import artifact_acceptance
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path.startswith("/api/artifacts/reports/") and path.endswith("/revise"):
        from uuid import uuid4
        from agentforge import brain_planner, task_history
        parts = path.split("/")
        if (len(parts) != 6 or set(request) != {"ack", "sha256", "content"}
                or request["ack"] != "PROPOSE_REPORT_REVISION"):
            raise ValueError("Invalid report revision request")
        ident = parts[4]
        sha = request["sha256"]
        if session is None or session.get("reviewed_reports", {}).get(ident) != sha:
            raise PermissionError("Inspect the exact report before proposing a revision")
        current = artifact_acceptance.inspect(ident, sha, "reports", db_path=server.task_db_path)
        if current["status"] != "REJECTED":
            raise PermissionError("Report revision requires a rejected source report")
        doc, _ = artifact_acceptance.source(ident, sha, "reports", db_path=server.task_db_path)
        if request["content"] == doc["content"]:
            raise ValueError("REPORT_REVISION_UNCHANGED")
        source = task_history.get_task(ident, db_path=server.task_db_path)
        return brain_planner.propose(
            "Chỉnh sửa báo cáo Markdown", "filesystem.revise_report",
            {"path": "report-revisions/" + uuid4().hex + ".md",
             "content": request["content"], "source_path": source["request"]["path"],
             "source_sha256": sha, "source_task_id": ident},
            db_path=server.brain_db_path)

    if path.startswith("/api/artifacts/reports/") and path.endswith("/decision"):
        parts = path.split("/")
        if (len(parts) != 6 or set(request) !=
                {"ack", "sha256", "expected_revision", "evidence_sha"}):
            raise ValueError("Invalid report decision")
        ident = parts[4]
        decision = {"ACCEPT_ARTIFACT": "ACCEPTED",
                    "REJECT_ARTIFACT": "REJECTED"}.get(request["ack"])
        if (decision is None or session is None or
                session.get("reviewed_reports", {}).get(ident) != request["sha256"]):
            raise PermissionError("Inspect exact report before deciding acceptance")
        from agentforge.ops_control import require_active
        require_active()
        return artifact_acceptance.decide(
            ident, request["sha256"], "reports", decision, confirm=True,
            expected_revision=request["expected_revision"],
            evidence_sha=request["evidence_sha"], db_path=server.task_db_path)
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
