"""S4 bounded company planner: fixed, auditable plans and skill selection.

No prompt-driven arbitrary code or unbounded recursive agents. Owner may
choose a business goal; only trusted templates produce executable steps.
"""
import json
from agentforge import brain_store, skill_registry, skill_runner

TEMPLATES = {
    "campaign.review": ("dataset",),
    "website.campaign": ("slug", "dataset"),
    "website.draft": ("slug", "brief"),
    "webapp.draft": ("slug", "brief"),
    "webapp.revision": ("slug", "brief", "source_proposal_id",
                        "source_sha256", "revision_feedback"),
    "webapp.qa": ("proposal_id", "sha256", "confirm_external_run"),
    "website.browser": ("slug",),
    "media.produce": ("slug", "title", "scenes"),
    "media.review": ("run_id",),
    "research.discovery": ("topic",),
    "creative.storyboard": ("topic", "audience", "goal"),
    "growth.review": ("campaign",),
    "growth.launch_local": ("campaign", "slug", "title", "scenes",
                            "description", "rights_attested"),
}
OPTIONAL = {"campaign", "photo_name", "rights_confirmed"}
ALIASES = {
    "campaign": "campaign.review", "website": "website.campaign",
    "browser": "website.browser", "media": "media.produce",
    "research": "research.discovery", "storyboard": "creative.storyboard",
    "growth": "growth.review",
}


def _steps(template, inputs):
    if template not in TEMPLATES:
        raise brain_store.BrainError("Unknown goal template; no arbitrary skill plan")
    required = set(TEMPLATES[template])
    if not isinstance(inputs, dict) or required - set(inputs):
        raise brain_store.BrainError("Required goal inputs missing")
    allowed = required | (
        {"source_proposal_id", "source_sha256", "revision_feedback"} if template == "website.draft" else
        {"campaign"} if template in {"campaign.review", "website.campaign"} else
        {"photo_name", "rights_confirmed"} if template == "media.produce" else set())
    if set(inputs) - allowed:
        raise brain_store.BrainError("Unexpected goal input fields")
    if template == "campaign.review":
        payload = {"dataset": inputs["dataset"]}
        if "campaign" in inputs:
            payload["campaign"] = inputs["campaign"]
        steps = [(name, dict(payload)) for name in (
            "analytics.quality_check", "analytics.content_report",
            "analytics.opportunity_score", "analytics.finance_report")]
    elif template == "website.draft":
        from agentforge.product_builder import _check_slug, _bounded_text
        _check_slug(inputs["slug"])
        _bounded_text(inputs["brief"], "brief", 20, 6000)
        revision_keys = {"source_proposal_id", "source_sha256", "revision_feedback"}
        present = revision_keys & set(inputs)
        if present and present != revision_keys:
            raise brain_store.BrainError("Revision requires the source ID, SHA and complete feedback")
        if present:
            from agentforge.website_feedback import MIN_FEEDBACK, MAX_FEEDBACK
            from agentforge.product_builder import _check_proposal_id, SHA_RE
            _check_proposal_id(inputs["source_proposal_id"])
            if not isinstance(inputs["source_sha256"], str) or not SHA_RE.fullmatch(inputs["source_sha256"]):
                raise brain_store.BrainError("Invalid source proposal digest")
            _bounded_text(inputs["revision_feedback"], "revision feedback", MIN_FEEDBACK, MAX_FEEDBACK)
        steps = [("web.create", {key: inputs[key] for key in
                 ("slug", "brief", "source_proposal_id", "source_sha256", "revision_feedback")
                 if key in inputs})]
    elif template in {"webapp.draft", "webapp.revision"}:
        from agentforge.webapp_builder import SLUG, PROPOSAL, SHA, _text, _name
        _name(inputs["slug"], SLUG, "slug")
        _text(inputs["brief"], "brief", 6000)
        if template == "webapp.revision":
            _name(inputs["source_proposal_id"], PROPOSAL, "source proposal id")
            digest = inputs["source_sha256"]
            if not isinstance(digest, str) or not SHA.fullmatch(digest):
                raise brain_store.BrainError("Invalid application source SHA")
            feedback = _text(inputs["revision_feedback"], "revision feedback", 3000)
            if len(feedback) < 10:
                raise brain_store.BrainError("Feedback must have 10+ characters")
        steps = [("webapp.create", dict(inputs))]
    elif template == "webapp.qa":
        from agentforge.webapp_builder import PROPOSAL, SHA, _name
        _name(inputs["proposal_id"], PROPOSAL, "proposal id")
        if (not isinstance(inputs["sha256"], str)
                or not SHA.fullmatch(inputs["sha256"])):
            raise brain_store.BrainError("Invalid app QA proposal digest")
        if inputs["confirm_external_run"] is not True:
            raise brain_store.BrainError("Owner must explicitly request external QA")
        steps = [("webapp.sandbox_test", dict(inputs))]
    elif template == "website.campaign":
        payload = {"dataset": inputs["dataset"]}
        if "campaign" in inputs:
            payload["campaign"] = inputs["campaign"]
        steps = [("web.quality_check", {"slug": inputs["slug"]})]
        steps += [(name, dict(payload)) for name in (
            "analytics.quality_check", "analytics.content_report",
            "analytics.opportunity_score", "analytics.finance_report")]
    elif template == "website.browser":
        steps = [("web.quality_check", {"slug": inputs["slug"]}),
                 ("web.browser_test", {"slug": inputs["slug"],
                                       "confirm_browser_run": True})]
    elif template == "media.produce":
        from agentforge.media_assets import _scenes, _slug, _text
        _slug(inputs["slug"])
        _text(inputs["title"], "title", 88)
        _scenes(inputs["scenes"])
        image = dict(inputs)
        steps = [("media.compose", image),
                 ("media.quality_check", {"run_id": {"from_step": 0, "field": "run_id"}}),
                 ("media.video_render", {"run_id": {"from_step": 0, "field": "run_id"},
                                          "confirm_external_run": True})]
    elif template == "media.review":
        steps = [("media.quality_check", {"run_id": inputs["run_id"]})]
    elif template == "research.discovery":
        steps = [("research.opportunity", {"topic": inputs["topic"]})]
    elif template == "growth.review":
        steps = [(skill_id, {"campaign": inputs["campaign"]}) for skill_id in (
            "growth.quality_check", "growth.report", "growth.reconcile")]
    elif template == "growth.launch_local":
        # Prepare for both channels; NO network publication or account access.
        # The owner must explicitly attest rights in the reviewed plan.
        from agentforge.media_assets import _scenes, _slug, _text
        from agentforge.growth_store import _identifier, CAMPAIGN, _text as growth_text
        _identifier(inputs["campaign"], CAMPAIGN, "campaign")
        _slug(inputs["slug"])
        _text(inputs["title"], "title", 88)
        _scenes(inputs["scenes"])
        growth_text(inputs["description"], max_length=1200, field="description")
        if inputs["rights_attested"] is not True:
            raise brain_store.BrainError("Owner must attest original/licensed media rights")
        binding = {"from_step": 0, "field": "run_id"}
        steps = [
            ("media.compose", {
                "slug": inputs["slug"], "title": inputs["title"],
                "scenes": inputs["scenes"]}),
            ("media.quality_check", {"run_id": binding}),
            ("media.video_render", {
                "run_id": binding, "confirm_external_run": True}),
        ]
        for channel in ("youtube", "tiktok"):
            steps.append(("growth.bundle_prepare", {
                "campaign": inputs["campaign"], "channel": channel,
                "run_id": binding, "title": inputs["title"],
                "description": inputs["description"],
                "confirm_rights": True, "confirm_write": True}))
        steps.append(("growth.quality_check", {"campaign": inputs["campaign"]}))
    else:
        steps = [("media.copy_draft", dict(inputs))]
    plan = []
    for skill_id, payload in steps:
        skill, required_permissions = skill_runner._contract(skill_id)
        for key, value in payload.items():
            if isinstance(value, dict) and set(value) == {"from_step", "field"}:
                if not (key == "run_id" and value["field"] == "run_id"
                        and type(value["from_step"]) is int
                        and 0 <= value["from_step"] < len(plan)):
                    raise brain_store.BrainError("Invalid output binding")
                check_payload = {**payload, key: "0" * 32}
                skill_registry.validate_payload(skill, check_payload)
            else:
                # Validate the whole payload below only after references filled.
                pass
        if not any(isinstance(v, dict) and "from_step" in v for v in payload.values()):
            skill_registry.validate_payload(skill, payload)
        plan.append({
            "skill_id": skill_id, "worker_id": skill["worker_id"],
            "payload": payload,
            "required_permissions": sorted(required_permissions),
            "estimated_model_calls": skill["limits"]["estimated_model_calls"],
            "external_process": "process.run" in required_permissions,
        })
    return plan


def make_plan(template, inputs, *, max_model_calls=0, max_external_runs=0):
    """Validate budgets at plan time; runtime still checks each action."""
    if type(max_model_calls) is not int or not 0 <= max_model_calls <= 3:
        raise brain_store.BrainError("Invalid model-call cap")
    if type(max_external_runs) is not int or not 0 <= max_external_runs <= 3:
        raise brain_store.BrainError("Invalid external-process cap")
    plan = _steps(template, inputs)
    estimated_model = sum(x["estimated_model_calls"] for x in plan)
    expected_external = sum(x["external_process"] for x in plan)
    if estimated_model > max_model_calls or expected_external > max_external_runs:
        raise brain_store.BrainError(
            "Declared model/process use exceeds goal cap; explicit owner cap needed")
    return plan


def propose(title, template, inputs, *, max_model_calls=0,
            max_external_runs=0, db_path=None):
    """Create draft for SHA-reviewed owner approval; cannot execute yet."""
    if template in ALIASES:
        template = ALIASES[template]
    plan = make_plan(template, inputs, max_model_calls=max_model_calls,
                     max_external_runs=max_external_runs)
    recorded = {**inputs, "_limits": {
        "max_model_calls": max_model_calls,
        "max_external_runs": max_external_runs,
    }}
    # Limits are stored in goal metadata, not passed to underlying skill.
    result = brain_store.create_goal(title, template, recorded, plan, db_path=db_path)
    result.update({
        "plan": [{"index": i, "skill_id": x["skill_id"],
                  "worker_id": x["worker_id"],
                  "required_permissions": x["required_permissions"]}
                 for i, x in enumerate(plan)],
        "limits": recorded["_limits"],
        "owner_approval_required": True,
        "execution_authorized": False,
        "spending_authorized": False,
    })
    return result


def resolve_payload(goal, index, *, task_db_path=None):
    """Only allow hardcoded reference to a successful previous run_id."""
    from agentforge import task_history
    plan = goal["plan"]
    step = plan[index]
    result = {}
    for key, value in step["payload"].items():
        if not isinstance(value, dict):
            result[key] = value
            continue
        if set(value) != {"from_step", "field"} or value["field"] != "run_id":
            raise brain_store.BrainError("Unsupported dataflow binding")
        source_index = value["from_step"]
        if type(source_index) is not int or source_index >= index or source_index < 0:
            raise brain_store.BrainError("Forward/cyclic dataflow reference forbidden")
        previous = next((x for x in goal["steps"]
                         if x["step_index"] == source_index), None)
        if previous is None or previous["status"] != "SUCCEEDED":
            raise brain_store.BrainError("Dependent step has not succeeded")
        from agentforge import task_history
        child = task_history.get_task(previous["child_task_id"], db_path=task_db_path)
        if child["status"] != "SUCCEEDED" or not isinstance(child["result"], dict):
            raise brain_store.BrainError("Missing immutable task result")
        inner = child["result"]
        run_id = inner.get("run_id")
        if (not isinstance(run_id, str) or len(run_id) != 32
                or not all(c in "0123456789abcdef" for c in run_id)):
            raise brain_store.BrainError("Malformed produced run_id")
        result[key] = run_id
    skill, _ = skill_runner._contract(step["skill_id"])
    skill_registry.validate_payload(skill, result)
    return result


def read_only_plan(template, inputs):
    plan = _steps(template, inputs)
    return all(skill_runner._contract(x["skill_id"])[0]["execution_mode"] == "read_only"
               for x in plan)
