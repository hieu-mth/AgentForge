"""Validate and bind the reviewed FLUX GGUF API graph."""
import copy
import json
import ntpath
import re
from urllib.parse import urlsplit

NODES = {
    "6": ("CLIPTextEncode", {"text", "clip"}),
    "8": ("VAEDecode", {"samples", "vae"}),
    "9": ("SaveImage", {"filename_prefix", "images"}),
    "27": ("EmptySD3LatentImage", {"width", "height", "batch_size"}),
    "31": ("KSampler", {"seed", "steps", "cfg", "sampler_name", "scheduler",
                        "denoise", "model", "positive", "negative", "latent_image"}),
    "33": ("CLIPTextEncode", {"text", "clip"}),
    "38": ("UnetLoaderGGUF", {"unet_name"}),
    "39": ("DualCLIPLoaderGGUF", {"clip_name1", "clip_name2", "type"}),
    "40": ("VAELoader", {"vae_name"}),
}
LINKS = {
    "6": {"clip": ["39", 0]}, "8": {"samples": ["31", 0], "vae": ["40", 0]},
    "9": {"images": ["8", 0]}, "33": {"clip": ["39", 0]},
    "31": {"model": ["38", 0], "positive": ["6", 0], "negative": ["33", 0],
           "latent_image": ["27", 0]},
}
MODEL_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,139}\.(?:gguf|safetensors)\Z", re.I)
FOLDER = re.compile(r"[A-Za-z0-9_-]{1,48}(?:/[A-Za-z0-9_-]{1,48}){0,3}\Z")
MAX_WORKFLOW_BYTES = 16_000
IMAGE_OPTION_LIMITS = {"max_resolution": (256, 1536), "max_steps": (1, 20), "timeout_seconds": (5, 600)}


def _integer(value, lower, upper, label):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("Invalid FLUX " + label)
    return value


def dimensions(width, height, steps, config):
    for value in (width, height):
        _integer(value, 256, config["max_resolution"], "resolution")
        if value % 16:
            raise ValueError("FLUX dimensions must be multiples of 16")
    return width, height, _integer(steps, 1, config["max_steps"], "steps")


def node_ids(graph):
    """Identify the approved topology by class and sampler conditioning links."""
    if not isinstance(graph, dict) or len(graph) != len(NODES):
        raise ValueError("Expected the nine-node FLUX API workflow")
    by_class = {}
    for key, node in graph.items():
        if (not isinstance(key, str) or not re.fullmatch(r"[0-9]{1,12}", key)
                or not isinstance(node, dict) or not isinstance(node.get("class_type"), str)):
            raise ValueError("Invalid FLUX API node")
        by_class.setdefault(node["class_type"], []).append(key)
    result = {}
    for role, (kind, _) in NODES.items():
        if kind == "CLIPTextEncode":
            continue
        matches = by_class.get(kind, [])
        if len(matches) != 1:
            raise ValueError("Expected exactly one FLUX node of class " + kind)
        result[role] = matches[0]
    sampler = graph[result["31"]].get("inputs")
    for role, field in (("6", "positive"), ("33", "negative")):
        link = sampler.get(field) if isinstance(sampler, dict) else None
        if (not isinstance(link, list) or len(link) != 2
                or link[0] not in by_class.get("CLIPTextEncode", []) or link[1] != 0):
            raise ValueError("Invalid FLUX text conditioning link")
        result[role] = link[0]
    if len(set(result.values())) != len(NODES):
        raise ValueError("Ambiguous FLUX text conditioning links")
    return result


def validate(config, model, endpoint):
    if not isinstance(config, dict) or set(config) != {
        "workflow", "max_resolution", "max_steps", "timeout_seconds", "output_dir"
    }:
        raise ValueError("Invalid FLUX runtime settings")
    if urlsplit(endpoint).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("FLUX requires an IPv4 loopback endpoint")
    for name, (lower, upper) in IMAGE_OPTION_LIMITS.items():
        _integer(config[name], lower, upper, name)
    folder = config["output_dir"]
    if (not isinstance(folder, str) or not FOLDER.fullmatch(folder)
            or any(ntpath.isreserved(part) for part in folder.split("/"))):
        raise ValueError("Output folder must be relative to the AgentForge workspace")
    graph = config["workflow"]
    ids = node_ids(graph)
    for key, (kind, fields) in NODES.items():
        node = graph[ids[key]]
        if (not isinstance(node, dict) or not {"inputs", "class_type"} <= node.keys()
                or node.keys() - {"inputs", "class_type", "_meta"} or node["class_type"] != kind
                or not isinstance(node["inputs"], dict) or node["inputs"].keys() != fields):
            raise ValueError("Invalid FLUX node " + key)
        meta = node.get("_meta", {})
        if (not isinstance(meta, dict) or meta.keys() - {"title"}
                or not isinstance(meta.get("title", ""), str) or len(meta.get("title", "")) > 120):
            raise ValueError("Invalid FLUX node metadata")
        for field, link in LINKS.get(key, {}).items():
            if node["inputs"][field] != [ids[link[0]], link[1]]:
                raise ValueError("Invalid FLUX graph link")
    inputs = {role: graph[key]["inputs"] for role, key in ids.items()}
    if (inputs["38"]["unet_name"] != model or not model.lower().endswith(".gguf")
            or inputs["39"]["type"] != "flux"):
        raise ValueError("FLUX loader model must match the registered GGUF")
    for filename in (model, inputs["39"]["clip_name1"], inputs["39"]["clip_name2"],
                     inputs["40"]["vae_name"]):
        if not isinstance(filename, str) or not MODEL_FILE.fullmatch(filename):
            raise ValueError("Invalid FLUX model filename")
    sampler = inputs["31"]
    if (inputs["27"]["batch_size"] != 1 or sampler["cfg"] != 1
            or sampler["denoise"] != 1 or sampler["sampler_name"] != "euler"
            or sampler["scheduler"] != "simple" or inputs["33"]["text"] != ""):
        raise ValueError("Unsupported FLUX Schnell sampling configuration")
    _integer(sampler["seed"], 0, 2**64 - 1, "workflow seed")
    dimensions(inputs["27"]["width"], inputs["27"]["height"], sampler["steps"], config)
    for value in (inputs["6"]["text"], inputs["9"]["filename_prefix"]):
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError("Invalid FLUX workflow text")
    try:
        encoded = json.dumps(graph, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
    except (UnicodeError, ValueError):
        raise ValueError("Invalid FLUX workflow JSON") from None
    if len(encoded) > MAX_WORKFLOW_BYTES:
        raise ValueError("FLUX workflow exceeds the 16000-byte limit")
    return config


def bind(config, job_id, prompt, width, height, seed, steps):
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise ValueError("Prompt must be 1–2000 characters")
    dimensions(width, height, steps, config)
    _integer(seed, 0, 2**53 - 1, "seed")
    graph = copy.deepcopy(config["workflow"])
    ids = node_ids(graph)
    graph[ids["6"]]["inputs"]["text"] = prompt.strip()
    graph[ids["27"]]["inputs"].update(width=width, height=height)
    graph[ids["31"]]["inputs"].update(seed=seed, steps=steps)
    graph[ids["9"]]["inputs"]["filename_prefix"] = "af_" + job_id
    return graph
