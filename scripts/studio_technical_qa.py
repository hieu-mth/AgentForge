"""Verify saved Studio artifacts without changing approval or creative QA state."""
import argparse
import io
import json

from PIL import Image

from agentforge.features.film_studio import draft_pipeline, studio_runtime


def _check(present, verify):
    if not present:
        return "NOT_VERIFIED"
    try:
        verify()
    except (OSError, ValueError, KeyError, SyntaxError):
        return "FAIL"
    return "PASS"


def review(job):
    moving = job["brief"].get("mode") == "motion"
    adapter = studio_runtime.motion_artifacts(job) if moving else None

    def verify_image(index):
        with Image.open(io.BytesIO(draft_pipeline.image(job, index))) as image:
            if image.format != "PNG":
                raise ValueError("Expected PNG")
            image.verify()

    def verify_video():
        with draft_pipeline.video_path(job).open("rb") as stream:
            draft_pipeline.verify_video(job, stream)

    shots = []
    for index, scene in enumerate(job.get("board", {}).get("scenes", [])):
        item = {"shot": index+1, "shot_id": scene.get("shot_id"),
                "image": _check(scene.get("asset"), lambda: verify_image(index))}
        if adapter:
            item["motion"] = _check(scene.get("motion_sha"), lambda: adapter.clip_path(scene))
        shots.append(item)
    return {"production_id": job["id"], "shots": shots,
            "final_mp4": _check(job.get("video_sha"), verify_video),
            "creative_quality": "NOT_VERIFIED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production_id")
    arguments = parser.parse_args()
    print(json.dumps(review(draft_pipeline._read(arguments.production_id)), indent=2))
