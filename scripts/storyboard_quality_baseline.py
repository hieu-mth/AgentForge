"""Export local evidence from a verified Studio production without changing it."""
import argparse
import io
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageOps

from agentforge.features.film_studio import draft_pipeline, studio_runtime
from agentforge.features.media.render import find_media_tool
from agentforge.paths import WORKSPACE_DIR, ensure_local_root


def export(production_id, output):
    job = draft_pipeline._read(production_id)
    video = draft_pipeline.video_path(job)
    with video.open("rb") as stream:
        draft_pipeline.verify_video(job, stream)
    receipt = json.loads(draft_pipeline.verified_receipt(job))
    ffmpeg = find_media_tool("ffmpeg")
    ffprobe = find_media_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("FFmpeg and ffprobe are required to export evidence")
    adapter = studio_runtime.motion_artifacts(job)
    shots = job["board"]["scenes"]
    output = ensure_local_root(output)
    if output.is_relative_to(WORKSPACE_DIR.resolve()):
        raise ValueError("Write baseline evidence outside the production workspace")
    output.mkdir(parents=True, exist_ok=False)
    sheet = Image.new("RGB", (768, 168 * len(shots)), "#151823")
    draw = ImageDraw.Draw(sheet)
    for index, shot in enumerate(shots):
        clip = adapter.clip_path(shot)
        frames = int(subprocess.check_output([
            ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(clip),
        ], timeout=30))
        if frames < 1:
            raise ValueError(f"No decoded frames for shot {index+1}")
        for column, frame in enumerate((0, frames // 2, frames - 1)):
            raw = subprocess.check_output([
                ffmpeg, "-nostdin", "-v", "error", "-threads", "1", "-i", str(clip),
                "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", "-c:v", "png",
                "-threads", "1", "-f", "image2pipe", "pipe:1",
            ], timeout=30)
            with Image.open(io.BytesIO(raw)) as image:
                image.save(output / f"shot-{index+1:02d}-frame-{frame:03d}.png")
                sheet.paste(ImageOps.contain(image.convert("RGB"), (256, 144)), (256 * column, 168 * index))
        draw.text((8, 168 * index + 147), f"Shot {index+1:02d}  |  first / middle / last", fill="white")
    sheet.save(output / "contact-sheet.png")
    report = {key: job.get(key) for key in (
        "id", "brief", "duration_plan", "board", "cast", "approved_motion", "studio_plan",
        "motion_revision", "resources", "storyboard_sha", "attempt_started_at", "attempt_finished_at")}
    report.update(receipt=receipt, creative_quality="NOT_VERIFIED")
    (output / "baseline.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt["technical"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production_id")
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    print(export(arguments.production_id, arguments.output))
