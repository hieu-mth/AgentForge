"""Validation of the currently supported ComfyUI profile options."""
from pathlib import Path

from agentforge.ai.orchestrator_policy import ModelConfigError
from agentforge.features.media import comfy_image_workflow, flux_workflow
from agentforge.features.film_studio import motion_ltx


def validate_settings(profile, options):
    result = {}
    if "flux" in options:
        result["flux"] = flux_workflow.validate(options["flux"], profile["model"], profile["base_url"])
    if "comfy_image" in options:
        result["comfy_image"] = comfy_image_workflow.validate(options["comfy_image"], profile["model"], profile["base_url"])
    if "motion_encoder" in options:
        encoder = options["motion_encoder"]
        if (not isinstance(encoder, str) or not 1 <= len(encoder) <= 512
                or not Path(encoder).is_absolute() or encoder.startswith(("\\\\", "//"))
                or any(ord(char) < 32 for char in encoder)):
            raise ModelConfigError("Motion encoder must be a local absolute file path")
        result["motion_encoder"] = encoder
    if "comfy_video" in options:
        workflow = motion_ltx.configured_workflow(options["comfy_video"], profile["model"])
        if Path(result["motion_encoder"]).name != workflow["api"]["2"]["inputs"]["clip_name"]:
            raise ModelConfigError("Encoder filename must match the configured video workflow")
        result["comfy_video"] = workflow
    return result
