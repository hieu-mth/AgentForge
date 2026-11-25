"""Owner-triggered visual review of a digest-bound Studio shot; never auto-approve."""
import hashlib
import io
import tempfile
from contextlib import nullcontext
from pathlib import Path

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_timeline, studio_vision
from agentforge.features.media import render, visual_jobs
from agentforge.paths import ensure_local_root


def sample_indices(scenes, index):
    start = sum(scene["frames"] for scene in scenes[:index])
    count = scenes[index]["frames"]
    points = [(start, "SHOT START"), (start + count // 2, "SHOT MID"),
              (start + count - 1, "SHOT END")]
    if start:
        points.insert(0, (start - 1, "PREVIOUS END"))
    # A very short technical segment can share start/mid/end frame.
    return list(dict(points).items())


def _sheet(items):
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError:
        raise ValueError("Install the media extra to review video frames") from None
    cols = 2
    size = (320, 180)
    cell_height = 204
    canvas = Image.new("RGB", (cols * size[0], ((len(items)+1)//2) * cell_height), "#242424")
    draw = ImageDraw.Draw(canvas)
    for i, (payload, label) in enumerate(items):
        with Image.open(io.BytesIO(payload)) as source:
            image = ImageOps.contain(source.convert("RGB"), size)
        x, y = i % cols * size[0], i // cols * cell_height
        draw.text((x+6, y+4), label, fill="white")
        canvas.paste(image, (x+(size[0]-image.width)//2, y+22+(size[1]-image.height)//2))
    for quality in (75, 60, 45, 30, 20):
        target = io.BytesIO()
        canvas.save(target, "JPEG", quality=quality, optimize=True)
        if target.tell() <= studio_vision.MAX_SHEET_BYTES:
            return target.getvalue()
    raise ValueError("Sampled contact sheet exceeds vision request budget")


def build_sheet(job, index):
    from agentforge.features.film_studio import draft_pipeline as draft
    scenes = job["board"]["scenes"]
    points = sample_indices(scenes, index)
    video = draft.video_path(job)
    with video.open("rb") as stream:
        draft.verify_video(job, stream)
    items = [(draft.image(job, index), "GENERATED IMAGE")]
    expression = "+".join("eq(n\\," + str(frame) + ")" for frame, _ in points)
    with tempfile.TemporaryDirectory(dir=draft._folder(job["id"]), prefix="qa-") as tmp:
        folder = ensure_local_root(Path(tmp))
        target = folder / "sample-%02d.png"
        render._run_process([render._ffmpeg(), "-nostdin", "-v", "error", "-xerror", "-threads", "1",
                             "-i", str(video), "-vf", "select=" + expression + ",scale=320:180:force_original_aspect_ratio=decrease",
                             "-fps_mode", "vfr", "-frames:v", str(len(points)), "-an",
                             "-threads", "1", str(target)], cwd=folder, timeout=90)
        for offset, (_, label) in enumerate(points, 1):
            path = ensure_local_root(folder / f"sample-{offset:02d}.png")
            if not path.is_file() or not 1 <= path.stat().st_size <= 1024 * 1024:
                raise ValueError("Could not extract exact visual review frames")
            items.append((path.read_bytes(), label))
    # Detect modifications during frame extraction.
    with video.open("rb") as stream:
        draft.verify_video(job, stream)
    return _sheet(items), [frame for frame, _ in points]


def review(job, data):
    from agentforge.features.film_studio import draft_pipeline as draft
    if (job["status"] != "REVIEW" or not job.get("storyboard_version")
            or not job.get("video_sha") or data.get("video_sha") != job["video_sha"]
            or data.get("sha256") != job.get("storyboard_sha")
            or data["sha256"] != job.get("approved_storyboard_sha")
            or data["sha256"] != draft_timeline.digest(job)):
        raise ValueError("Video hoặc storyboard đã thay đổi. Hãy tải lại trước khi đánh giá.")
    if type(data.get("allow_cloud")) is not bool:
        raise ValueError("Explicit cloud image review consent required")
    scenes = job["board"]["scenes"]
    index = draft._number(data["index"], 0, len(scenes)-1)
    scene = scenes[index]
    ops_control.require_active()
    revision, profile, limit = model_hub.vision_binding()
    cloud = profile["provider"] in {"openai", "anthropic", "chatgpt"}
    if cloud and not data["allow_cloud"]:
        raise PermissionError("Cần xác nhận gửi frame video cho model cloud.")
    # Only local inference is serialized; extracting sample frames is a local tool.
    with (nullcontext() if cloud else model_hub.local_inference_slot()):
        sheet, indices = build_sheet(job, index)
        ops_control.require_active()
        current_revision, current_profile, current_limit = model_hub.vision_binding()
        if (current_revision, current_profile, current_limit) != (revision, profile, limit):
            raise ValueError("Model Hub changed during visual review; retry with current settings")
        if cloud:
            limit = min(limit, job.get("cloud_call_limit", limit))
            used = job.get("cloud_calls", 0)
            if used >= limit:
                raise ValueError("Đã hết ngân sách lượt gọi AI cloud của production.")
            job.update(cloud_calls=used+1, cloud_call_limit=limit)
            draft._save(job)
        # Context contains only the intended shot and relevant adjacent boundary, not credentials.
        context = {"shot": {key: scene[key] for key in draft_timeline.STORY_FIELDS if key in scene},
                   "cast": {key: job.get("cast", {}).get(key) for key in scene.get("character_ids", [])},
                   "continuity": job["board"]["continuity"],
                   "previous_shot": scenes[index-1].get("description") if index else None,
                   "next_shot": scenes[index+1].get("description") if index+1 < len(scenes) else None}
        result = studio_vision.infer(profile, context, sheet)
    report = {**result, "scope": "SAMPLED_FRAMES_ADVISORY", "model_id": profile["id"],
              "model": profile["model"], "provider": profile["provider"], "model_revision": revision,
              "storyboard_sha": job["storyboard_sha"], "video_sha": job["video_sha"],
              "shot_id": scene["shot_id"], "asset_sha": scene["asset"],
              "motion_sha": scene.get("motion_sha"), "frame_indices": indices,
              "contact_sheet_sha": hashlib.sha256(sheet).hexdigest(), "created_at": visual_jobs._now()}
    # Keep only current shot reports; old reports cannot apply to a different video version.
    reviews = job.setdefault("visual_reviews", {})
    reviews = {key: value for key, value in reviews.items()
               if value.get("video_sha") == job["video_sha"]}
    reviews[scene["shot_id"]] = report
    job["visual_reviews"] = reviews
    draft._save(job)
    return job


MAX_BATCH = 8
MAX_REPAIRS = 2


def current_review(job, scene):
    report = job.get("visual_reviews", {}).get(scene["shot_id"], {})
    if (report.get("video_sha") == job.get("video_sha")
            and report.get("storyboard_sha") == job.get("storyboard_sha")
            and report.get("asset_sha") == scene.get("asset")
            and report.get("motion_sha") == scene.get("motion_sha")
            and report.get("shot_id") == scene["shot_id"]):
        return report
    return None


def _check_current(job, data):
    if (job.get("status") != "REVIEW" or not job.get("video_sha")
            or data.get("video_sha") != job["video_sha"]
            or data.get("sha256") != job.get("storyboard_sha")
            or data.get("sha256") != job.get("approved_storyboard_sha")
            or data.get("sha256") != draft_timeline.digest(job)):
        raise ValueError("Video hoặc storyboard đã thay đổi. Hãy tải lại.")


def review_batch(job, data):
    _check_current(job, data)
    if type(data.get("allow_cloud")) is not bool:
        raise ValueError("Explicit cloud image review consent required")
    limit = data.get("max_reviews")
    if type(limit) is not int or not 1 <= limit <= MAX_BATCH:
        raise ValueError("Review batch must contain 1–8 shots.")
    pending = [i for i, scene in enumerate(job["board"]["scenes"]) if not current_review(job, scene)]
    # Each completed review is persisted independently; no hidden retry or auto-approval.
    for i in pending[:limit]:
        job = review(job, {**data, "index": i})
    return job


def repair_targets(job, data):
    _check_current(job, data)
    limit = data.get("max_repairs")
    if type(limit) is not int or not 1 <= limit <= MAX_REPAIRS:
        raise ValueError("Repair limit must be 1–2 shots.")
    remaining = MAX_REPAIRS - job.get("qa_repairs", 0)
    if remaining <= 0:
        raise ValueError("Đã hết ngân sách sửa cảnh tự động của production.")
    targets = []
    for i, scene in enumerate(job["board"]["scenes"]):
        report = current_review(job, scene)
        if report and report.get("verdict") == "FAIL":
            targets.append((i, report))
    if not targets:
        raise ValueError("Không có cảnh FAIL đã được đánh giá trên phiên bản hiện tại.")
    return targets[:min(limit, remaining)]
