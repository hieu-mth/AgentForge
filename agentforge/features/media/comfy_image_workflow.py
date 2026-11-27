"""Bounded ComfyUI image workflow dialects; no arbitrary custom-node execution.

The original FLUX graph remains a strictly validated dialect. Standard
checkpoint graphs may select any compatible installed checkpoint, independent
of its model family. Both share the same execution and visual receipt path.
"""
import copy
import json
import math
import ntpath
import re
from urllib.parse import urlsplit

from agentforge.features.media import flux_workflow

MAX_WORKFLOW_BYTES = flux_workflow.MAX_WORKFLOW_BYTES
FOLDER = flux_workflow.FOLDER

_CHECKPOINT_NODES = {
    "38": ("CheckpointLoaderSimple", {"ckpt_name"}),
    "6": ("CLIPTextEncode", {"text", "clip"}),
    "33": ("CLIPTextEncode", {"text", "clip"}),
    "27": ("EmptyLatentImage", {"width", "height", "batch_size"}),
    "31": ("KSampler", flux_workflow.NODES["31"][1]),
    "8": ("VAEDecode", {"samples", "vae"}),
    "9": ("SaveImage", {"filename_prefix", "images"}),
}
_CHECKPOINT_LINKS = {
    "6": {"clip": ("38", 1)}, "33": {"clip": ("38", 1)},
    "31": {"model": ("38", 0), "positive": ("6", 0), "negative": ("33", 0),
           "latent_image": ("27", 0)},
    "8": {"samples": ("31", 0), "vae": ("38", 2)},
    "9": {"images": ("8", 0)},
}
_SAMPLERS = frozenset({"euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde", "heun", "ddim"})
_SCHEDULERS = frozenset({"normal", "simple", "karras", "exponential", "ddim_uniform", "sgm_uniform"})


def _checkpoint(graph):
    return isinstance(graph, dict) and any(isinstance(node, dict)
        and node.get("class_type") == "CheckpointLoaderSimple" for node in graph.values())


def node_ids(graph):
    if not _checkpoint(graph):
        return flux_workflow.node_ids(graph)
    if len(graph) != len(_CHECKPOINT_NODES):
        raise ValueError("Expected seven-node checkpoint image API workflow")
    classes = {}
    for key, node in graph.items():
        if (not isinstance(key, str) or not re.fullmatch(r"[0-9]{1,12}", key)
                or not isinstance(node, dict) or not isinstance(node.get("class_type"), str)):
            raise ValueError("Invalid checkpoint workflow node")
        classes.setdefault(node["class_type"], []).append(key)
    ids = {}
    for role, (kind, _) in _CHECKPOINT_NODES.items():
        if kind == "CLIPTextEncode":
            continue
        if len(classes.get(kind, ())) != 1:
            raise ValueError("Expected exactly one checkpoint workflow node: " + kind)
        ids[role] = classes[kind][0]
    sampler = graph[ids["31"]].get("inputs", {})
    if not isinstance(sampler, dict):
        raise ValueError("Invalid checkpoint sampler inputs")
    for role, field in (("6", "positive"), ("33", "negative")):
        link = sampler.get(field)
        if (not isinstance(link, list) or len(link) != 2
                or not isinstance(link[0], str) or link[0] not in classes.get("CLIPTextEncode", ())
                or type(link[1]) is not int or link[1] != 0):
            raise ValueError("Invalid checkpoint text conditioning link")
        ids[role] = link[0]
    if len(set(ids.values())) != len(_CHECKPOINT_NODES):
        raise ValueError("Ambiguous checkpoint conditioning")
    return ids


def model_fields(graph):
    return ({"38": ("ckpt_name",)} if _checkpoint(graph)
            else {"38": ("unet_name",), "39": ("clip_name1", "clip_name2"), "40": ("vae_name",)})


def validate(config, model, endpoint):
    if not isinstance(config, dict) or not _checkpoint(config.get("workflow")):
        return flux_workflow.validate(config, model, endpoint)
    if set(config) != {"workflow", "max_resolution", "max_steps", "timeout_seconds", "output_dir"}:
        raise ValueError("Invalid ComfyUI image workflow settings")
    if urlsplit(endpoint).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("ComfyUI image workflow requires IPv4 loopback")
    for name, minimum, maximum in (("max_resolution", 256, 1536), ("max_steps", 1, 20),
                                    ("timeout_seconds", 5, 600)):
        if type(config[name]) is not int or not minimum <= config[name] <= maximum:
            raise ValueError("Invalid ComfyUI " + name)
    folder = config["output_dir"]
    if (not isinstance(folder, str) or not FOLDER.fullmatch(folder)
            or any(ntpath.isreserved(part) for part in folder.split("/"))):
        raise ValueError("Output folder must be relative to the AgentForge workspace")
    graph = config["workflow"]
    ids = node_ids(graph)
    for role, (kind, fields) in _CHECKPOINT_NODES.items():
        node = graph[ids[role]]
        if (not {"class_type", "inputs"} <= node.keys() or node.keys() - {"class_type", "inputs", "_meta"}
                or node["class_type"] != kind or not isinstance(node["inputs"], dict)
                or node["inputs"].keys() != fields):
            raise ValueError("Invalid checkpoint workflow inputs: " + kind)
        meta = node.get("_meta", {})
        if (not isinstance(meta, dict) or meta.keys() - {"title"}
                or not isinstance(meta.get("title", ""), str) or len(meta.get("title", "")) > 120):
            raise ValueError("Invalid checkpoint node metadata")
        for field, (target, slot) in _CHECKPOINT_LINKS.get(role, {}).items():
            if node["inputs"][field] != [ids[target], slot]:
                raise ValueError("Invalid checkpoint workflow link")
    inputs = {role: graph[key]["inputs"] for role, key in ids.items()}
    if (not isinstance(model, str) or inputs["38"]["ckpt_name"] != model or not flux_workflow.MODEL_FILE.fullmatch(model)
            or not model.lower().endswith(".safetensors")):
        raise ValueError("Checkpoint loader must match the registered safetensors model")
    sampler = inputs["31"]
    if (type(inputs["27"]["batch_size"]) is not int or inputs["27"]["batch_size"] != 1
            or not isinstance(sampler["sampler_name"], str) or sampler["sampler_name"] not in _SAMPLERS
            or not isinstance(sampler["scheduler"], str) or sampler["scheduler"] not in _SCHEDULERS
            or type(sampler["cfg"]) not in (int, float) or not math.isfinite(sampler["cfg"])
            or not 1 <= sampler["cfg"] <= 12
            or type(sampler["denoise"]) not in (int, float) or sampler["denoise"] != 1
            or type(sampler["seed"]) is not int or not 0 <= sampler["seed"] <= 2**64 - 1):
        raise ValueError("Unsupported checkpoint sampling settings")
    dimensions(inputs["27"]["width"], inputs["27"]["height"], sampler["steps"], config)
    for value in (inputs["6"]["text"], inputs["33"]["text"], inputs["9"]["filename_prefix"]):
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError("Invalid checkpoint workflow text")
    if len(json.dumps(graph, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")) > MAX_WORKFLOW_BYTES:
        raise ValueError("Workflow exceeds byte limit")
    return config


def dimensions(width, height, steps, config):
    for value in (width, height):
        if type(value) is not int or not 256 <= value <= config["max_resolution"] or value % 16:
            raise ValueError("Invalid ComfyUI image dimensions")
    if type(steps) is not int or not 1 <= steps <= config["max_steps"]:
        raise ValueError("Invalid ComfyUI image steps")
    return width, height, steps


def bind(config, job_id, prompt, width, height, seed, steps):
    if not _checkpoint(config["workflow"]):
        return flux_workflow.bind(config, job_id, prompt, width, height, seed, steps)
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise ValueError("Prompt must be 1–2000 characters")
    if type(seed) is not int or not 0 <= seed <= 2**53 - 1:
        raise ValueError("Invalid ComfyUI seed")
    dimensions(width, height, steps, config)
    graph = copy.deepcopy(config["workflow"])
    ids = node_ids(graph)
    graph[ids["6"]]["inputs"]["text"] = prompt.strip()
    graph[ids["27"]]["inputs"].update(width=width, height=height)
    graph[ids["31"]]["inputs"].update(seed=seed, steps=steps)
    graph[ids["9"]]["inputs"]["filename_prefix"] = "af_" + job_id
    return graph


def profile_config(profile):
    """Legacy FLUX profiles keep strict validation and their stored shape."""
    if "comfy_image" in profile:
        return validate(profile["comfy_image"], profile["model"], profile["base_url"])
    return flux_workflow.validate(profile["flux"], profile["model"], profile["base_url"])
