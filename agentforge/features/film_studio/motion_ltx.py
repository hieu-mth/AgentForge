"""Pinned single-pass LTX-Video I2V pilot graph and input preparation."""
import hashlib
import json
import re
from pathlib import Path

from agentforge.integrations import comfyui
from agentforge.paths import ensure_local_root

MODEL_ID = "ltxv-2b-0.9.8-distilled-fp8"
CHECKPOINT = MODEL_ID + ".safetensors"
CHECKPOINT_SHA = "d6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15"
ENCODER = "t5xxl_fp8_e4m3fn.safetensors"
ENCODER_SHA = "7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09"
FORMAT = "agentforge.film.comfy.ltx_i2v.v1"
CONFIGURED_FORMAT = "agentforge.film.comfy.i2v.v2"
MAX_CONFIG_BYTES = 16000
MAX_CONFIG_FRAMES = 97
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


def configured_output(record):
    """Bounded output of the supported I2V graph dialect, not a VRAM estimate."""
    size = record["api"]["6"]["inputs"]
    result = {"width": size["width"], "height": size["height"], "frames": size["length"],
              "fps": record["api"]["12"]["inputs"]["fps"], "batch_size": 1}
    w, h, frames, fps = (result[key] for key in ("width", "height", "frames", "fps"))
    if (any(type(v) is not int for v in (w, h, frames, fps))
            or not (256 <= w <= 640 and 256 <= h <= 640 and w % 32 == h % 32 == 0)
            or not 9 <= frames <= MAX_CONFIG_FRAMES or (frames - 1) % 8
            or not 8 <= fps <= 30 or frames > fps * 5
            or w * h * frames > 512 * 288 * 49):
        raise ValueError("Video workflow exceeds the bounded I2V output budget")
    return result


def _safe_weight(name):
    return (isinstance(name, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,139}\\.safetensors", name, re.I)
            and name.casefold() != "wan2.2_ti2v_5b_fp16.safetensors")


def configured_workflow(record, model=None):
    """Validate a configurable checkpoint/encoder with a known safe graph topology.

    No arbitrary custom nodes, altered sampler or filesystem/URL bindings.
    Future graph dialects belong at this boundary, not in the production core.
    """
    try:
        if not isinstance(record, dict) or record.get("format") != CONFIGURED_FORMAT:
            raise ValueError("Expected configured I2V workflow wrapper")
        output = configured_output(record)
        checkpoint = record["api"]["1"]["inputs"]["ckpt_name"]
        encoder = record["api"]["2"]["inputs"]["clip_name"]
        if (not _safe_weight(checkpoint) or not _safe_weight(encoder)
                or checkpoint.casefold() == encoder.casefold() or (model is not None and model != checkpoint)):
            raise ValueError("Video workflow weights must match the registered safe checkpoint")
        hashes = record["weights_sha256"]
        if (not isinstance(hashes, dict) or set(hashes) != {"checkpoint", "encoder"}
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in hashes.values())):
            raise ValueError("Configured video requires both weight SHA-256 digests")
        expected = workflow(49)
        expected.update(format=CONFIGURED_FORMAT, weights_sha256=hashes)
        graph = expected["api"]
        graph["1"]["inputs"]["ckpt_name"] = checkpoint
        graph["2"]["inputs"]["clip_name"] = encoder
        graph["6"]["inputs"].update(width=output["width"], height=output["height"], length=output["frames"])
        graph["7"]["inputs"]["frame_rate"] = output["fps"]
        graph["12"]["inputs"]["fps"] = output["fps"]
        canonical = json.dumps(record, sort_keys=True, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
        if len(canonical.encode("utf-8")) > MAX_CONFIG_BYTES or canonical != json.dumps(
                expected, sort_keys=True, allow_nan=False, ensure_ascii=False, separators=(",", ":")):
            raise ValueError("Unsupported video graph topology or sampling settings")
        return record
    except (KeyError, TypeError, IndexError, RecursionError) as exc:
        raise ValueError("Invalid configured I2V workflow") from exc


def configured_weights(record):
    return {record["api"]["1"]["inputs"]["ckpt_name"]: record["weights_sha256"]["checkpoint"],
            record["api"]["2"]["inputs"]["clip_name"]: record["weights_sha256"]["encoder"]}


def verify_configured_weights(record, installation, encoder_path, *, metadata_only=False):
    configured_workflow(record)
    checkpoint = record["api"]["1"]["inputs"]["ckpt_name"]
    encoder = record["api"]["2"]["inputs"]["clip_name"]
    files = ((Path(installation) / "ComfyUI" / "models" / "checkpoints" / checkpoint,
              checkpoint, record["weights_sha256"]["checkpoint"], 6 * 1024**3),
             (Path(encoder_path), encoder, record["weights_sha256"]["encoder"], 5 * 1024**3))
    for path, name, digest, limit in files:
        path = ensure_local_root(path)
        if (path.name != name or not path.is_file() or not 1 <= path.stat().st_size <= limit):
            raise ValueError("Missing or oversized configured video weight")
        if not metadata_only:
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError("Configured video weight SHA-256 mismatch")


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


def check_runtime(port, *, require_models=False, frames=33, record=None):
    """Check core node inputs without sending an execution request."""
    checked = {}
    graph = configured_workflow(record) if record is not None else workflow(frames)
    for node in graph["api"].values():
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
