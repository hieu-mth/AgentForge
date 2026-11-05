import re
import tomllib
from pathlib import Path
from agentforge.paths import REPOSITORY_ROOT

from agentforge.ai.model_registry import load_models


ROOT = REPOSITORY_ROOT

WORKER_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")

ALLOWED_FIELDS = {
    "id",
    "model_ref",
    "runtime",
    "capabilities",
}

SUPPORTED_RUNTIMES = {"langgraph", "manual"}


class WorkerConfigError(ValueError):
    pass


def load_worker(worker_id: str, *, root=None) -> dict:
    if (
        not isinstance(worker_id, str)
        or not WORKER_ID_PATTERN.fullmatch(worker_id)
    ):
        raise WorkerConfigError("Invalid worker ID")

    project_root = Path(root) if root is not None else ROOT
    folder = project_root / "workers" / worker_id

    config_path = folder / "worker.toml"
    instructions_path = folder / "instructions.md"

    if not config_path.is_file():
        raise WorkerConfigError(
            f"Worker configuration not found: {worker_id}"
        )

    try:
        content = config_path.read_text(encoding="utf-8-sig")
        config = tomllib.loads(content)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise WorkerConfigError(
            f"Cannot read worker configuration: {worker_id}"
        ) from exc

    unknown_fields = set(config) - ALLOWED_FIELDS

    if unknown_fields:
        raise WorkerConfigError(
            f"Unauthorized configuration fields: {sorted(unknown_fields)}"
        )

    if config.get("id") != worker_id:
        raise WorkerConfigError("Worker ID does not match folder")

    runtime = config.get("runtime")

    if runtime not in SUPPORTED_RUNTIMES:
        raise WorkerConfigError("Unsupported worker runtime")

    capabilities = config.get("capabilities")

    if (
        not isinstance(capabilities, list)
        or not capabilities
        or any(
            not isinstance(item, str) or not item.strip()
            for item in capabilities
        )
        or len(set(capabilities)) != len(capabilities)
    ):
        raise WorkerConfigError("Invalid worker capabilities")

    models = load_models(project_root / "config" / "models.toml")

    model_ref = config.get("model_ref")

    if not isinstance(model_ref, str) or model_ref not in models:
        raise WorkerConfigError(
            f"Unknown model reference: {model_ref}"
        )

    selected_model = models[model_ref]

    if not selected_model["enabled"]:
        raise WorkerConfigError(
            f"Model is disabled: {model_ref}"
        )

    if not instructions_path.is_file():
        raise WorkerConfigError("Worker instructions not found")

    instructions = instructions_path.read_text(
        encoding="utf-8-sig"
    )

    if not instructions.strip():
        raise WorkerConfigError("Worker instructions are empty")

    return {
        "id": worker_id,
        "runtime": runtime,
        "model_ref": model_ref,
        "model": selected_model,
        "capabilities": capabilities,
        "instructions": instructions,
    }
