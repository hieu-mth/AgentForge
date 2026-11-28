"""Pinned single-pass LTX-Video I2V pilot graph and input preparation."""
import hashlib
import json
from pathlib import Path

from agentforge.integrations import comfyui
from agentforge.paths import ensure_local_root

MODEL_ID = "ltxv-2b-0.9.8-distilled-fp8"
CHECKPOINT = MODEL_ID + ".safetensors"
CHECKPOINT_SHA = "d6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15"
ENCODER = "t5xxl_fp8_e4m3fn.safetensors"
ENCODER_SHA = "7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09"
FORMAT = "agentforge.film.comfy.ltx_i2v.v1"
PROFILE = {"width": 512, "height": 288, "frames": 33, "fps": 24, "batch_size": 1}
FRAME_PRESETS = (33, 49)
EXTENDED_MIN_COMMIT_MIB = 20 * 1024
# Lightricks 0.9.8 distilled first-pass knots, with Comfy's terminal zero.
SIGMAS = "1.0, 0.9937, 0.9875, 0.9812, 0.9750, 0.9094, 0.7250, 0.0"


def profile(frames):
    if type(frames) is not int or frames not in FRAME_PRESETS:
        raise ValueError("Unknown LTX pilot frame preset")
    return {**PROFILE, "frames": frames}


def workflow(frames=33):
    preset = profile(frames)
    graph = {
        "1": ("CheckpointLoaderSimple", {"ckpt_name": CHECKPOINT}),
        "2": ("CLIPLoader", {"clip_name": ENCODER, "type": "ltxv", "device": "default"}),
        "3": ("CLIPTextEncode", {"clip": ["2", 0], "text": ""}),
        "4": ("CLIPTextEncode", {"clip": ["2", 0], "text": ""}),
        "5": ("LoadImage", {"image": "af_motion_source_placeholder.png"}),
        "6": ("LTXVImgToVideo", {"positive": ["3", 0], "negative": ["4", 0],
                               "image": ["5", 0], "vae": ["1", 2], "width": preset["width"],
                               "height": preset["height"], "length": preset["frames"],
                               "batch_size": preset["batch_size"], "strength": 1.0}),
        "7": ("LTXVConditioning", {"positive": ["6", 0], "negative": ["6", 1], "frame_rate": preset["fps"]}),
        "8": ("KSamplerSelect", {"sampler_name": "euler"}),
        "9": ("ManualSigmas", {"sigmas": SIGMAS}),
        "10": ("SamplerCustom", {"model": ["1", 0], "add_noise": True, "noise_seed": 0, "cfg": 1.0,
                                "positive": ["7", 0], "negative": ["7", 1], "sampler": ["8", 0],
                                "sigmas": ["9", 0], "latent_image": ["6", 2]}),
        "11": ("VAEDecode", {"samples": ["10", 0], "vae": ["1", 2]}),
        "12": ("CreateVideo", {"images": ["11", 0], "fps": preset["fps"]}),
        "13": ("SaveVideo", {"video": ["12", 0], "filename_prefix": "af_motion_placeholder",
                             "format": "mp4", "format.codec": "h264"}),
    }
    return {"format": FORMAT, "positive_node": "3", "image_node": "5", "seed_node": "10",
            "output_node": "13", "api": {
                key: {"class_type": node, "inputs": inputs} for key, (node, inputs) in graph.items()
            }}


def _weight_file(path, name, size):
    path = ensure_local_root(Path(path))
    if path.name != name or not path.is_file() or path.stat().st_size != size:
        raise ValueError("Missing or invalid LTX weights: " + name)
    return path


def verify_weights(installation, encoder_path, *, metadata_only=False):
    files = (
        (Path(installation) / "ComfyUI" / "models" / "checkpoints" / CHECKPOINT,
         CHECKPOINT, 4_461_695_684, CHECKPOINT_SHA),
        (encoder_path, ENCODER, 4_893_934_904, ENCODER_SHA),
    )
    for path, name, size, sha in files:
        path = _weight_file(path, name, size)
        if metadata_only:
            continue
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                raise ValueError("LTX weights SHA-256 mismatch: " + name)


def check_runtime(port, *, require_models=False, frames=33):
    """Check core node inputs without sending an execution request."""
    checked = {}
    for node in workflow(frames)["api"].values():
        kind = node["class_type"]
        if kind not in checked:
            payload = comfyui.request_image_bytes("/object_info/" + kind, port=port)
            definition = json.loads(payload).get(kind, {})
            groups = definition.get("input", {})
            checked[kind] = {**groups.get("required", {}), **groups.get("optional", {})}
        fields = checked[kind]
        inputs = node["inputs"]
        if kind == "SaveVideo":
            options = fields.get("format", [None, {}])[1].get("options", [])
            output = next((row for row in options if row["key"] == inputs["format"]), {})
            codec = output.get("inputs", {}).get("required", {}).get("codec", [None, {}])
            if inputs["format.codec"] not in [row["key"] for row in codec[1].get("options", [])]:
                raise ValueError("LTX MP4/H.264 output is unavailable")
            fields = {**fields, "format.codec": ["STRING"]}
        if not inputs.keys() <= fields.keys():
            raise ValueError("LTX node inputs unavailable: " + kind)
        for field, value in node["inputs"].items():
            if isinstance(value, list) or field == "image":
                continue
            if not require_models and field in {"ckpt_name", "clip_name"}:
                continue
            spec = fields[field]
            if spec and isinstance(spec[0], list) and value not in spec[0]:
                raise ValueError(f"LTX node value unavailable: {kind}.{field}")
            bounds = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            if isinstance(value, (int, float)) and (
                    value < bounds.get("min", value) or value > bounds.get("max", value)):
                raise ValueError(f"LTX node value outside runtime range: {kind}.{field}")
            if kind == "LTXVImgToVideo" and field == "length":
                minimum, step = bounds.get("min"), bounds.get("step")
                if type(minimum) is not int or type(step) is not int or step < 1 or (value - minimum) % step:
                    raise ValueError("LTX frame preset does not match runtime length step")
    return sorted(checked)
