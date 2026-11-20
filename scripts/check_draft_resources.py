"""Opt-in, isolated three-draft memory acceptance on an Owner machine."""
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

# Allow invocation as python scripts/check_draft_resources.py from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_pipeline as drafts, draft_resources
from agentforge.features.media import flux_runtime, visual_jobs
from agentforge.paths import WORKSPACE_DIR, ensure_local_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-inference", action="store_true", required=True)
    parser.parse_args()
    _, bindings = model_hub.draft_routes()
    profile = bindings["image.generate"]
    status = flux_runtime.readiness(profile["flux"], urlsplit(profile["base_url"]).port)
    if status != "READY":
        raise SystemExit("Live inference not run: " + status)
    root = ensure_local_root(WORKSPACE_DIR / "resource-acceptance" / uuid4().hex)
    root.mkdir(parents=True)
    drafts.DB = root / "drafts.sqlite3"
    visual_jobs.DB = root / "visuals.sqlite3"
    drafts.WORKSPACE_DIR = flux_runtime.WORKSPACE_DIR = root
    print(root, flush=True)
    ideas = (
        "Mèo cam nhặt chiếc lá vàng và mang về chiếc giỏ dưới tán cây.",
        "Thuyền giấy đi qua hai đoạn suối nhỏ trong khu rừng buổi sáng.",
        "Chú chim xanh tìm một quả mọng rồi trở về tổ trong khu vườn.",
    )
    with (root / "samples.jsonl").open("x", encoding="utf-8") as stream:
        for index, idea in enumerate(ideas, 1):
            ident = uuid4().hex
            job = drafts.submit({"id": ident, "idea": idea, "seconds": 6,
                                 "ratio": "16:9", "scene_count": 2})
            deadline = time.monotonic() + 3600
            while job["status"] in {"QUEUED", "RUNNING"}:
                point = {"clip": index, "stage": job["stage"], **draft_resources.snapshot()}
                stream.write(json.dumps(point) + "\n")
                stream.flush()
                if time.monotonic() >= deadline:
                    drafts.act(ident, "cancel", {})
                    raise SystemExit("Acceptance timeout: cancellation requested at the next checkpoint")
                time.sleep(5)
                job = drafts._read(ident)
            point = {"clip": index, "status": job["status"], **draft_resources.snapshot()}
            stream.write(json.dumps(point) + "\n")
            stream.flush()
            (root / f"clip-{index}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"clip {index}: {job['status']}", flush=True)
            if job["status"] != "REVIEW":
                raise SystemExit(job.get("error") or job["status"])
            with drafts.video_path(job).open("rb") as video:
                drafts.verify_video(job, video)
    print("LIVE PASS: three verified MP4 drafts", flush=True)


if __name__ == "__main__":
    main()
