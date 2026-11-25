"""Build paired text-to-image and img2img graphs offline for character reference evaluation."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path

from PIL import Image

from agentforge.ai import model_hub
from agentforge.features.media import flux_workflow


def prepare(database, reference, prompts, seed, steps, denoise):
    revision, bindings = model_hub.draft_routes(db_path=database, moving=False)
    profile = bindings["image.generate"]
    config = flux_workflow.validate(profile["flux"], profile["model"], profile["base_url"])
    if not 0 < denoise < 1:
        raise ValueError("Choose a denoise strength between zero and one")
    data = reference.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG":
            raise ValueError("Expected a PNG reference")
        width, height = image.size
        image.verify()
    pairs = []
    for index, prompt in enumerate(prompts, 1):
        control = flux_workflow.bind(config, f"control_{index}", prompt, width, height, seed, steps)
        candidate = copy.deepcopy(control)
        ids = flux_workflow.node_ids(control)
        loader = str(max(map(int, control)) + 1)
        candidate[loader] = {"class_type": "LoadImage", "inputs": {"image": digest + ".png"}}
        candidate[ids["27"]] = {"class_type": "VAEEncode", "inputs": {
            "pixels": [loader, 0], "vae": [ids["40"], 0]}}
        candidate[ids["31"]]["inputs"]["denoise"] = denoise
        candidate[ids["9"]]["inputs"]["filename_prefix"] = f"af_candidate_{index}"
        pairs.append({"control": control, "candidate": candidate})
    return {"revision": revision, "model": profile["model"], "reference_sha256": digest,
            "dimensions": [width, height], "executed": False, "pairs": pairs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--prompt", action="append", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--denoise", type=float, required=True)
    args = parser.parse_args()
    result = prepare(args.database, args.reference, args.prompt, args.seed, args.steps, args.denoise)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
