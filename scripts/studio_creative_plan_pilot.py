"""Run local Ollama creative planning against an existing authored script, read-only."""
import argparse
from itertools import groupby
import json
from pathlib import Path

from agentforge.ai import model_hub
from agentforge.features.film_studio import creative_plan, draft_pipeline, studio_runtime
from agentforge.paths import WORKSPACE_DIR, ensure_local_root


def plan(production_id):
    job = draft_pipeline._read(production_id)
    duration = job.get("duration_plan", {})
    if not duration.get("content_scene_count") or job["brief"].get("mode") != "motion":
        raise ValueError("The pilot requires a duration-planned authored motion production")
    _, bindings, _ = draft_pipeline._studio_bindings(job)
    profile = bindings["film.storyboard"]
    script = job["brief"]["idea"]
    scenes = []
    for number, grouped in groupby(duration["shots"], key=lambda shot: shot["content_scene"]):
        shots = list(grouped)
        start, end = shots[0]["script_range"]
        context = draft_pipeline._scene_beats(script[start:end], last=number == duration["content_scene_count"])
        scenes.append({"scene": number, "source_range": [start, end],
                       "frames": sum(shot["script_shot_frames"] for shot in shots), **context})
    globals_ = [item for scene in scenes for item in scene["global_constraints"]]
    output = studio_runtime.job_output(job)
    drafts = []
    with model_hub.local_inference_slot():
        for scene in scenes:
            drafts.append(creative_plan.propose_scene(scene, globals_, output.fps,
                lambda instructions, payload, schema: studio_runtime.text_adapter(profile).infer_structured(
                    profile, instructions, payload, schema, cpu_only=True)))
    return {"production_id": production_id, "model": profile["model"],
            **creative_plan.compile_plan(scenes, drafts, output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production_id")
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    target = ensure_local_root(arguments.output)
    if target.is_relative_to(WORKSPACE_DIR.resolve()):
        raise ValueError("Write pilot evidence outside the production workspace")
    result = plan(arguments.production_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f"{result['total_frames']} frames across {len(result['scenes'])} content scenes")
