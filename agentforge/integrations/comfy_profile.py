"""Validation of the currently supported ComfyUI profile options."""
from pathlib import Path

from agentforge.ai.orchestrator_policy import ModelConfigError
from agentforge.features.media import flux_workflow


def validate_settings(profile, options):
    result = {}
    if "flux" in options:
        result["flux"] = flux_workflow.validate(options["flux"], profile["model"], profile["base_url"])
    if "motion_encoder" in options:
        encoder = options["motion_encoder"]
        if (not isinstance(encoder, str) or not 1 <= len(encoder) <= 512
                or not Path(encoder).is_absolute() or encoder.startswith(("\\\\", "//"))
                or any(ord(char) < 32 for char in encoder)):
            raise ModelConfigError("Motion encoder must be a local absolute file path")
        result["motion_encoder"] = encoder
    return result
