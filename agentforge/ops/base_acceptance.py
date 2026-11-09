"""Wave 5: read-only Base V1 acceptance overview, not a product GO decision.

Inspects existing trusted setup/health/model configuration. This command makes
NO model calls, HTTP requests, backup copies, SQLite mutations, or subprocess
calls. A clean CI checkout cannot substitute for Owner machine acceptance.
Only bounded status summaries are printed; never expose prompts, paths, tokens
or model credentials.
"""
import argparse
import json

from agentforge.ai import model_hub
from agentforge.ops import preflight
from agentforge import ops_doctor


def _check(identifier, status, message):
    return {"id": identifier, "status": status, "detail": message}


def inspect(*, environment=None, health=None, models=None):
    """Read-only status report. Inject inputs only for deterministic fixture tests."""
    checks = []
    if environment is None:
        try:
            environment = preflight.inspect()
        except (OSError, ValueError, PermissionError, TypeError, KeyError):
            environment = {"status": "BLOCKED"}
    status = environment.get("status") if isinstance(environment, dict) else None
    if status not in {"BLOCKED", "REVIEW_REQUIRED", "READY_LOCAL_UNVERIFIED"}:
        status = "BLOCKED"
    checks.append(_check(
        "local_environment",
        "FAIL" if status == "BLOCKED" else
        "REVIEW_REQUIRED" if status == "REVIEW_REQUIRED" else "PASS",
        "Trusted source/config and local tools only; runtime versions for Node/npm unverified.",
    ))

    if health is None:
        try:
            health = ops_doctor.inspect()
        except (OSError, ValueError, PermissionError, TypeError, KeyError):
            health = {"status": "FAIL", "registry_valid": False, "backup_count": 0,
                      "running_tasks": 0, "running_goals": 0}
    hstatus = health.get("status") if isinstance(health, dict) else None
    if hstatus not in {"PASS", "REVIEW_REQUIRED", "FAIL"}:
        hstatus = "FAIL"
    checks.append(_check(
        "local_storage_and_operations",
        "FAIL" if hstatus == "FAIL" else
        "REVIEW_REQUIRED" if hstatus == "REVIEW_REQUIRED" else "PASS",
        "Read-only SQLite integrity, operations state, heartbeat and backup inventory.",
    ))

    if models is None:
        try:
            models = model_hub.catalog()
        except (OSError, ValueError, PermissionError, TypeError, KeyError):
            models = {}
    routes = models.get("routes") if isinstance(models, dict) else None
    if not isinstance(routes, list):
        routes = []
    wired = [r for r in routes if isinstance(r, dict)
             and r.get("kind") == "text" and r.get("execution") == "wired"]
    text_configured = sum(r.get("status") == "ROUTED" for r in wired)
    mismatched = sum(r.get("status") in {"INCOMPATIBLE", "INVALID_CONFIG"}
                     for r in wired)
    checks.append(_check(
        "text_model_route_configuration",
        "FAIL" if not wired or mismatched else
        "REVIEW_REQUIRED" if text_configured != len(wired) else "PASS",
        "Text route definitions only. No endpoint/model inference or cloud billing verified.",
    ))
    checks.extend([
        _check("owner_login_dashboard_real_machine", "UNVERIFIED",
               "Owner must log in on the actual local Windows Dashboard."),
        _check("model_inference_real_machine", "UNVERIFIED",
               "Owner-approved model inference/cost evidence not collected."),
        _check("task_approval_artifact_real_machine", "UNVERIFIED",
               "Temporary CI fixtures do not prove real artifact quality."),
        _check("backup_restore_real_machine", "UNVERIFIED",
               "Real backup/staged restore needs explicit Owner consent and inspection."),
    ])
    fail = any(item["status"] == "FAIL" for item in checks)
    return {
        "schema": 1,
        "status": "BLOCKED" if fail else "OWNER_REVIEW_REQUIRED",
        "checks": checks,
        "text_routes_configured": text_configured,
        "text_routes_expected": len(wired),
        "backup_count": (health.get("backup_count", 0)
                         if isinstance(health, dict) and
                         type(health.get("backup_count", 0)) is int else 0),
        "code_contract_tests_run_by_report": False,
        "owner_machine_verified": False,
        "generated_artifact_qa_verified": False,
        "provider_billing_verified": False,
        "production_go": False,
        "network_called": False,
        "inference_invoked": False,
        "local_data_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only Base V1 readiness, not real-model acceptance")
    parser.add_argument("--strict", action="store_true",
                        help="Exit nonzero unless all checks PASS (always requires Owner steps)")
    args = parser.parse_args()
    result = inspect()
    # Windows PowerShell 5.1 can use cp1252; escaped JSON is ASCII safe.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if result["status"] == "BLOCKED" or (
            args.strict and result["status"] != "PASS"):
        parser.exit(2)


if __name__ == "__main__":
    main()
