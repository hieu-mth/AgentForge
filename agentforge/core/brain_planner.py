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
    "webapp.develop": ("slug", "brief"),
    "webapp.company": ("slug", "brief"),
    "webapp.revision": ("slug", "brief", "source_proposal_id",
                        "source_sha256", "revision_feedback"),
    "webapp.source_revision": ("slug", "brief", "source_proposal_id",
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
# Exact producer/field/length contracts for V5 output bindings. No arbitrary
# LLM-selected paths or fields are allowed to flow between skills.
V5_BINDINGS = {
    ("webapp.develop", "architecture_id"): ("webapp.architect", "architecture_id", 32),
    ("webapp.develop", "architecture_sha"): ("webapp.architect", "architecture_sha", 64),
    ("webapp.audit", "proposal_id"): ("webapp.develop", "proposal_id", 32),
    ("webapp.audit", "sha256"): ("webapp.develop", "sha256", 64),
    ("webapp.review", "architecture_id"): ("webapp.architect", "architecture_id", 32),
    ("webapp.review", "architecture_sha"): ("webapp.architect", "architecture_sha", 64),
    ("webapp.review", "proposal_id"): ("webapp.develop", "proposal_id", 32),
    ("webapp.review", "sha256"): ("webapp.develop", "sha256", 64),
    ("webapp.review", "qa_report_id"): ("webapp.audit", "qa_report_id", 32),
    ("webapp.review", "qa_report_sha"): ("webapp.audit", "qa_report_sha", 64),
}

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
    elif template == "webapp.source_revision":
        from agentforge.webapp_builder import SLUG, PROPOSAL, SHA, _name, _text
        _name(inputs["slug"], SLUG, "revision slug")
        _text(inputs["brief"], "brief", 6000)
        _name(inputs["source_proposal_id"], PROPOSAL, "source proposal id")
        if (not isinstance(inputs["source_sha256"], str) or
                not SHA.fullmatch(inputs["source_sha256"])):
            raise brain_store.BrainError("Invalid AI React source SHA")
        feedback = _text(inputs["revision_feedback"], "revision feedback", 3000)
        if len(feedback) < 10:
            raise brain_store.BrainError("Feedback must have 10+ characters")
        steps = [("webapp.develop", dict(inputs))]
    elif template in {"webapp.develop", "webapp.company"}:
        from agentforge.webapp_builder import SLUG, _name, _text
        _name(inputs["slug"], SLUG, "slug")
        _text(inputs["brief"], "brief", 6000)
        if template == "webapp.develop":
            steps = [("webapp.develop", dict(inputs))]
        else:
            # Four fixed roles and only three explicit model calls. Static QA
            # checks provenance only; no build/browser/process is auto-started.
            bind = lambda index, field: {"from_step":index,"field":field}
            steps = [
                ("webapp.architect", dict(inputs)),
                ("webapp.develop", {**inputs,
                    "architecture_id":bind(0,"architecture_id"),
                    "architecture_sha":bind(0,"architecture_sha")}),
                ("webapp.audit", {
                    "proposal_id":bind(1,"proposal_id"),
                    "sha256":bind(1,"sha256")}),
                ("webapp.review", {
                    "architecture_id":bind(0,"architecture_id"),
                    "architecture_sha":bind(0,"architecture_sha"),
                    "proposal_id":bind(1,"proposal_id"),
                    "sha256":bind(1,"sha256"),
                    "qa_report_id":bind(2,"qa_report_id"),
                    "qa_report_sha":bind(2,"qa_report_sha")}),
            ]
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
        validated = dict(payload)
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            if set(value) != {"from_step", "field"}:
                raise brain_store.BrainError("Untrusted nested goal input")
            ref_idx, field = value["from_step"], value["field"]
            if type(ref_idx) is not int or not 0 <= ref_idx < len(plan):
                raise brain_store.BrainError("Invalid output binding index")
            if key == "run_id" and field == "run_id":
                size = 32  # preserve older vetted media / growth bindings
            else:
                contract = V5_BINDINGS.get((skill_id, key))
                if (contract is None or field != contract[1]
                        or plan[ref_idx]["skill_id"] != contract[0]):
                    raise brain_store.BrainError("Unauthorized V5 output binding")
                size = contract[2]
            validated[key] = "0" * size
        skill_registry.validate_payload(skill, validated)
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
    """Only allow typed, allowlisted previous-step refs and signed SHA values."""
    from agentforge import task_history
    plan = goal["plan"]
    step = plan[index]
    result = {}
    for key, value in step["payload"].items():
        if not isinstance(value, dict):
            result[key] = value
            continue
        if set(value) != {"from_step", "field"}:
            raise brain_store.BrainError("Unsupported dataflow binding")
        source_index = value["from_step"]
        field = value["field"]
        if type(source_index) is not int or source_index >= index or source_index < 0:
            raise brain_store.BrainError("Forward/cyclic dataflow reference forbidden")
        if key == "run_id" and field == "run_id":
            size = 32
        else:
            contract = V5_BINDINGS.get((step["skill_id"], key))
            if (contract is None or field != contract[1]
                    or plan[source_index]["skill_id"] != contract[0]):
                raise brain_store.BrainError("Unauthorized V5 dataflow binding")
            size = contract[2]
        previous = next((x for x in goal["steps"]
                         if x["step_index"] == source_index), None)
        if previous is None or previous["status"] != "SUCCEEDED":
            raise brain_store.BrainError("Dependent step has not succeeded")
        child = task_history.get_task(previous["child_task_id"], db_path=task_db_path)
        if child["status"] != "SUCCEEDED" or not isinstance(child["result"], dict):
            raise brain_store.BrainError("Missing immutable task result")
        output = child["result"].get(field)
        if (not isinstance(output, str) or len(output) != size
                or not all(c in "0123456789abcdef" for c in output)):
            raise brain_store.BrainError("Malformed signed produced output")
        result[key] = output
    skill, _ = skill_runner._contract(step["skill_id"])
    skill_registry.validate_payload(skill, result)
    return result


def read_only_plan(template, inputs):
    plan = _steps(template, inputs)
    return all(skill_runner._contract(x["skill_id"])[0]["execution_mode"] == "read_only"
               for x in plan)
