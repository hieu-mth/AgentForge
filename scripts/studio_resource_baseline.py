"""Summarize recorded Studio samples without inferring peaks or running jobs."""
import argparse
from collections import defaultdict
from datetime import datetime
import json

from agentforge.features.film_studio import draft_pipeline, motion_verify
from agentforge.features.media import visual_jobs


def summarize(job):
    samples = defaultdict(list)
    elapsed = defaultdict(list)
    for point in job.get("resources", []):
        operation = point["operation"]
        before, after = point.get("before"), point.get("after")
        samples[operation].extend(sample for sample in (before, after) if sample)
        if before and after and before.get("checked_at") and after.get("checked_at"):
            elapsed[operation].append((datetime.fromisoformat(after["checked_at"])
                                      - datetime.fromisoformat(before["checked_at"])).total_seconds())
    result = {"production_id": job["id"], "measurement": "STAGE_BOUNDARY_SNAPSHOTS",
              "attempt_started_at": job.get("attempt_started_at"),
              "attempt_finished_at": job.get("attempt_finished_at"), "operations": {}}
    for operation, points in samples.items():
        summary = {"sample_count": len(points), "paired_measurements": len(elapsed[operation]),
                   "paired_wall_seconds": round(sum(elapsed[operation]), 3) if elapsed[operation] else None}
        for field, label, reducer in (("ram_available", "min_ram_available_bytes", min),
                                      ("commit_used", "max_commit_used_bytes", max),
                                      ("vram_free_mib", "min_vram_free_mib", min)):
            values = [point[field] for point in points if type(point.get(field)) is int]
            summary[label] = reducer(values) if values else None
        result["operations"][operation] = summary
    shots = []
    for scene in job.get("board", {}).get("scenes", []):
        image = visual_jobs.runtime_details(scene["job_id"]) if scene.get("job_id") else None
        clip = motion_verify.inspect_receipt(scene["motion_job"]) if scene.get("motion_sha") else None
        shots.append({"shot_id": scene.get("shot_id"), "image_seconds": (image or {}).get("duration_seconds"),
                      "motion_submit_to_import_seconds": (clip or {}).get("wall_seconds_from_submission_to_import")})
    return {**result, "shots": shots}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production_id")
    arguments = parser.parse_args()
    print(json.dumps(summarize(draft_pipeline._read(arguments.production_id)), indent=2))
