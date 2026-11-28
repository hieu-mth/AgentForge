"""Validation of the currently supported ComfyUI profile options."""
from pathlib import Path

from agentforge.ai.orchestrator_policy import ModelConfigError
from agentforge.features.media import comfy_image_workflow, flux_workflow
from agentforge.features.film_studio import motion_ltx


def _image_fields(key, max_bytes):
    labels = {"max_resolution": "Cạnh ảnh tối đa (px)", "max_steps": "Số bước tối đa",
              "timeout_seconds": "Thời gian chờ (giây)"}
    defaults = {"max_resolution": 1024, "max_steps": 4, "timeout_seconds": 180}
    return [
        {"path": [key, "workflow"], "kind": "json", "label": "Workflow API JSON",
         "max_bytes": max_bytes, "required": True},
        *({"path": [key, name], "kind": "integer", "label": labels[name], "min": low,
           "max": high, "default": defaults[name], "required": True}
          for name, (low, high) in flux_workflow.IMAGE_OPTION_LIMITS.items()),
        {"path": [key, "output_dir"], "kind": "text", "label": "Thư mục con trong workspace",
         "default": "visuals", "required": True},
    ]


_ENCODER_FIELD = {"path": ["motion_encoder"], "kind": "text",
                  "label": "Đường dẫn tuyệt đối tới encoder video", "required": True,
                  "placeholder": "C:/models/encoder.safetensors", "max_length": 512}

# These options are also the allowlisted sets used by backend validation.
OPTION_VARIANTS = (
    {"id": "metadata", "label": "Chỉ đăng ký metadata", "fields": []},
    {"id": "flux", "label": "Ảnh · FLUX GGUF API", "fields": _image_fields("flux", flux_workflow.MAX_WORKFLOW_BYTES)},
    {"id": "comfy_image", "label": "Ảnh · Checkpoint API", "fields": _image_fields("comfy_image", comfy_image_workflow.MAX_WORKFLOW_BYTES)},
    {"id": "motion_encoder", "label": "Video · Preset tương thích cũ", "fields": [_ENCODER_FIELD]},
    {"id": "comfy_video", "label": "Video · Workflow I2V/T2V",
     "fields": [_ENCODER_FIELD, {"path": ["comfy_video"], "kind": "json",
                "label": "Workflow video local (I2V/T2V JSON)", "required": True,
                "max_bytes": motion_ltx.MAX_CONFIG_BYTES,
                "help": "Backend kiểm tra graph, SHA-256 weights và giới hạn tài nguyên."}]},
)


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
