"""Read-only referenced-entity validation before owner approval/execution.

No schema mutation, model calls or external APIs. Validate only references
needed by an already allowlisted S4 template. All lookup errors are stable,
safe codes; never include arbitrary user input, local paths or credentials.
"""
from agentforge import analytics_store, growth_store

ANALYTICS_TEMPLATES = frozenset({"campaign.review", "website.campaign"})
GROWTH_TEMPLATES = frozenset({"growth.review", "growth.launch_local"})


def inspect(template, inputs, *, analytics_db_path=None, growth_db_path=None):
    from agentforge.brain_planner import ALIASES, TEMPLATES
    name = ALIASES.get(template, template) if isinstance(template, str) else ""
    findings = []
    if name not in TEMPLATES:
        findings.append({"code": "UNKNOWN_TEMPLATE",
                         "field": "template",
                         "message": "Chọn workflow có sẵn trong Control Center."})
    elif not isinstance(inputs, dict):
        findings.append({"code": "INVALID_INPUT",
                         "field": "inputs",
                         "message": "Đầu vào phải là một JSON object."})
    else:
        if name in ANALYTICS_TEMPLATES:
            dataset = inputs.get("dataset")
            try:
                meta = analytics_store.dataset_metadata(
                    dataset, db_path=analytics_db_path)
            except (ValueError, TypeError):
                meta = None
            if meta is None:
                findings.append({
                    "code": "DATASET_NOT_FOUND", "field": "dataset",
                    "message": "Không tìm thấy dataset trong Intelligence. Chọn một dataset hiện có."})
        if name in GROWTH_TEMPLATES:
            try:
                growth_store.campaign_info(inputs.get("campaign"),
                                           db_path=growth_db_path)
            except (ValueError, KeyError, TypeError):
                findings.append({
                    "code": "CAMPAIGN_NOT_FOUND", "field": "campaign",
                    "message": "Không tìm thấy campaign trong Growth & Revenue."})
    return {"status": "READY" if not findings else "BLOCKED",
            "ready": not findings, "issues": findings,
            "model_called": False, "network_called": False,
            "source": "LOCAL_DATA_ONLY"}


def require_ready(template, inputs, *, analytics_db_path=None, growth_db_path=None):
    outcome = inspect(template, inputs, analytics_db_path=analytics_db_path,
                      growth_db_path=growth_db_path)
    if not outcome["ready"]:
        issue = outcome["issues"][0]
        raise ValueError(f'{issue["code"]}: {issue["message"]}')
    return outcome
