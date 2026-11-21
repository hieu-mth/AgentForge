"""Pinned single-pass LTX-Video I2V pilot graph and input preparation."""
import hashlib
import http.client
import json
import re
from pathlib import Path
from uuid import uuid4

from agentforge.features.media import visual_jobs
from agentforge.integrations import comfyui
from agentforge.paths import ensure_local_root

MODEL_ID = "ltxv-2b-0.9.8-distilled-fp8"
CHECKPOINT = MODEL_ID + ".safetensors"
CHECKPOINT_SHA = "d6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15"
ENCODER = "t5xxl_fp8_e4m3fn.safetensors"
ENCODER_SHA = "7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09"
FORMAT = "agentforge.film.comfy.ltx_i2v.v1"
PROFILE = {"width": 512, "height": 288, "frames": 33, "fps": 24, "batch_size": 1}
# Lightricks 0.9.8 distilled first-pass knots, with Comfy's terminal zero.
SIGMAS = "1.0, 0.9937, 0.9875, 0.9812, 0.9750, 0.9094, 0.7250, 0.0"
MAX_INPUT_BYTES = 8 * 1024 * 1024


def workflow():
    graph = {
        "1": ("CheckpointLoaderSimple", {"ckpt_name": CHECKPOINT}),
        "2": ("CLIPLoader", {"clip_name": ENCODER, "type": "ltxv", "device": "default"}),
        "3": ("CLIPTextEncode", {"clip": ["2", 0], "text": ""}),
        "4": ("CLIPTextEncode", {"clip": ["2", 0], "text": ""}),
        "5": ("LoadImage", {"image": "af_motion_source_placeholder.png"}),
        "6": ("LTXVImgToVideo", {"positive": ["3", 0], "negative": ["4", 0],
                               "image": ["5", 0], "vae": ["1", 2], "width": PROFILE["width"],
                               "height": PROFILE["height"], "length": PROFILE["frames"],
                               "batch_size": PROFILE["batch_size"], "strength": 1.0}),
        "7": ("LTXVConditioning", {"positive": ["6", 0], "negative": ["6", 1], "frame_rate": PROFILE["fps"]}),
        "8": ("KSamplerSelect", {"sampler_name": "euler"}),
        "9": ("ManualSigmas", {"sigmas": SIGMAS}),
        "10": ("SamplerCustom", {"model": ["1", 0], "add_noise": True, "noise_seed": 0, "cfg": 1.0,
                                "positive": ["7", 0], "negative": ["7", 1], "sampler": ["8", 0],
                                "sigmas": ["9", 0], "latent_image": ["6", 2]}),
        "11": ("VAEDecode", {"samples": ["10", 0], "vae": ["1", 2]}),
        "12": ("CreateVideo", {"images": ["11", 0], "fps": PROFILE["fps"]}),
        "13": ("SaveVideo", {"video": ["12", 0], "filename_prefix": "af_motion_placeholder",
                             "format": "mp4", "format.codec": "h264"}),
    }
    return {"format": FORMAT, "positive_node": "3", "image_node": "5", "seed_node": "10",
            "output_node": "13", "api": {
                key: {"class_type": node, "inputs": inputs} for key, (node, inputs) in graph.items()
            }}


def read_source(job_id, expected_sha):
    details = visual_jobs.runtime_details(job_id)
    if not details or not details.get("workflow_sha256"):
        raise ValueError("LTX requires a saved FLUX image")
    with visual_jobs.open_image_for_job(job_id) as (source, digest):
        if digest != expected_sha:
            raise PermissionError("FLUX source SHA does not match Owner review")
        data = source.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("LTX source must be a bounded PNG")
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise PermissionError("FLUX source changed during read")
    return data


def _verify_weights(path, name, size, sha):
    path = ensure_local_root(Path(path))
    if path.name != name or not path.is_file() or path.stat().st_size != size:
        raise ValueError("Missing or invalid LTX weights: " + name)
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
            raise ValueError("LTX weights SHA-256 mismatch: " + name)


def verify_weights(installation, encoder_path):
    _verify_weights(Path(installation) / "ComfyUI" / "models" / "checkpoints" / CHECKPOINT,
                    CHECKPOINT, 4_461_695_684, CHECKPOINT_SHA)
    _verify_weights(encoder_path, ENCODER, 4_893_934_904, ENCODER_SHA)


def check_runtime(port, *, require_models=False):
    """Check core node inputs without sending an execution request."""
    checked = {}
    for node in workflow()["api"].values():
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
    return sorted(checked)


def upload_source(port, job_id, data):
    """One bounded loopback upload with a generated basename and no overwrite."""
    if not re.fullmatch(r"[0-9a-f]{32}", job_id) or not 0 < len(data) <= MAX_INPUT_BYTES:
        raise ValueError("Invalid LTX input upload")
    name = "af_motion_source_" + job_id + ".png"
    boundary = uuid4().hex
    prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
              "Content-Type: image/png\r\n\r\n").encode("ascii")
    body = prefix + data + f"\r\n--{boundary}--\r\n".encode("ascii")
    with_connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        with_connection.request("POST", "/upload/image", body=body, headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
        })
        response = with_connection.getresponse()
        if response.status != 200:
            raise ValueError("ComfyUI did not accept the LTX input")
        raw = response.read(4097)
        if len(raw) > 4096:
            raise ValueError("Invalid ComfyUI upload response")
        saved = json.loads(raw)
        if saved != {"name": name, "subfolder": "", "type": "input"}:
            raise ValueError("ComfyUI returned an unexpected input filename")
    finally:
        with_connection.close()
    return name
