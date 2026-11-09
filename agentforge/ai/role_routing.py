"""V4.3: auditable role-to-model routing, local-first and no fallback.

Routing is fixed by reviewed worker.toml files. A global override is explicit
configuration, never a task/LLM suggestion. This module does not call models.
"""
import os
from agentforge.ai.model_registry import load_models, ModelConfigError
from agentforge.ai import model_hub
from agentforge.ai.worker_registry import load_worker

ROLE_WORKERS = {
    "architect": "webapp_architect",
    "developer": "webapp_developer",
    "reviewer": "webapp_reviewer",
}
MAX_PIPELINE_MODEL_CALLS = 3


def describe_role(role, *, root=None, model_ref_override=None, cloud_consent=False):
    if role not in ROLE_WORKERS:
        raise ValueError("Unknown AI role")
    worker = ROLE_WORKERS[role]
    profile = load_worker(worker, root=root)
    models = load_models(root / "config" / "models.toml" if root is not None else None)
    if root is None:
        models = model_hub.effective_models()
        selected, _, _ = model_hub.model_for_worker(worker, profile["model_ref"])
        ref = model_ref_override if model_ref_override is not None else selected
    else:
        ref = model_ref_override if model_ref_override is not None else profile["model_ref"]
    if not isinstance(ref, str) or ref not in models or not models[ref]["enabled"]:
        raise ModelConfigError("Unknown or disabled role model")
    model = models[ref]
    if model["provider"] != "ollama" and cloud_consent is not True:
        raise PermissionError("CLOUD_MODEL_CONSENT_REQUIRED")
    return {
        "role": role, "worker_id": worker,
        "model_ref": ref, "provider": model["provider"],
        "model_name": model["model"],
        "calls": 1, "remote": model["provider"] != "ollama",
        "fallback_allowed": False,
        "pricing_verified": False,
    }


def pipeline_plan(*, max_model_calls=3, cloud_consent=False, root=None,
                  model_ref_override=None):
    if type(max_model_calls) is not int or not 0 <= max_model_calls <= MAX_PIPELINE_MODEL_CALLS:
        raise ValueError("Invalid model call cap")
    selected = [describe_role(role, root=root,
                              model_ref_override=model_ref_override,
                              cloud_consent=cloud_consent)
                for role in ("architect", "developer", "reviewer")]
    if len(selected) > max_model_calls:
        raise PermissionError("MODEL_BUDGET_EXCEEDED")
    return {"roles": selected, "model_calls": len(selected),
            "external_runs": 0,
            "automatic_fallback": False, "auto_spend": False,
            "cost_verified": False}


def require_worker_model(worker_id):
    """Called before V5 model calls: deny cloud without explicit process opt-in."""
    if worker_id not in ROLE_WORKERS.values():
        raise ValueError("Unknown V5 worker")
    worker = load_worker(worker_id)
    override = os.environ.get("AGENTFORGE_MODEL_REF")
    route_ref, _, _ = model_hub.model_for_worker(worker_id, worker["model_ref"])
    ref = override or route_ref
    models = model_hub.effective_models()
    if ref not in models or not models[ref]["enabled"]:
        raise ModelConfigError("Unknown or disabled V5 model")
    if models[ref]["provider"] != "ollama" and os.getenv(
            "AGENTFORGE_CLOUD_MODEL_CONSENT") != "YES":
        raise PermissionError("CLOUD_MODEL_CONSENT_REQUIRED")
    return {"worker_id": worker_id, "model_ref": ref,
            "provider": models[ref]["provider"], "fallback_allowed": False}
