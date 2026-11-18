"""Trusted local ComfyUI image transport for Film Studio and media jobs.

Only reviewed image workflows are accepted; arbitrary graph execution is forbidden.
All image requests are restricted to the loopback ComfyUI allowlist.
"""
import json
import re
import secrets
import urllib.error
import urllib.request

from agentforge.integrations import comfyui as _comfyui

BASE = "http://127.0.0.1:8188"
CHECKPOINT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.(?:safetensors|ckpt)\Z")
IMAGE_FILE = re.compile(r"af_[a-f0-9]{32}_[a-zA-Z0-9_.-]{1,80}\.png\Z")
MAX_IMAGE = 6 * 1024 * 1024


def _request(path, *, payload=None, max_bytes=262144, timeout=5, opener=None):
    _comfyui.validate_image_route(path, has_body=payload is not None)
    if opener is None:
        return _comfyui.request_image_bytes(
            path, body=payload, timeout=timeout, max_response_bytes=max_bytes)
    body = None if payload is None else json.dumps(
        payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="GET" if body is None else "POST")
    with opener(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("Local ComfyUI returned non-success status")
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Local image response exceeds size limit")
    return raw


def health(*, opener=None):
    """Discover local checkpoints without starting a model job."""
    try:
        data = json.loads(_request("/models/checkpoints", opener=opener, timeout=3))
        if not isinstance(data, list):
            raise ValueError("Invalid checkpoint response")
        models = sorted({name for name in data
                         if isinstance(name, str) and CHECKPOINT.fullmatch(name)})
        return {"status": "READY" if models else "NO_CHECKPOINT",
                "checkpoints": models[:32], "truncated": len(models) > 32,
                "generation_invoked": False}
    except (OSError, RuntimeError, ValueError, TypeError, urllib.error.URLError):
        return {"status": "UNAVAILABLE", "checkpoints": [],
                "generation_invoked": False}


def _workflow(job_id, prompt, checkpoint):
    """Fixed standard-node graph; no external model-selected code."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "text, watermark, logo, distorted anatomy",
                         "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 768, "height": 512, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": secrets.randbelow(2**32), "steps": 20,
                         "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal",
                         "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0],
                         "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "af_" + job_id,
                         "images": ["6", 0]}},
    }
