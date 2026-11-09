"""Sanitized public task metadata shared by the Owner HTTP API.

Keep request content, absolute local paths and model output out of public summaries.
"""


def _task_public(task):
    """Only stable metadata, never request bodies or model outputs."""
    return {key: task[key] for key in (
        "task_id", "kind", "skill_id", "parent_id", "status",
        "created_at", "updated_at", "error"
    )}


def _artifact_names(result):
    """Expose only bounded artifact basenames, never absolute local paths."""
    found = []

    def visit(value, depth=0):
        if depth > 4 or len(found) >= 12:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"report_path", "proposal_path", "project_path",
                           "preview_path", "screenshot_path", "image_path",
                           "video_path", "audio_path", "caption_path"} and isinstance(item, str):
                    label = item.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
                    if label and label not in found:
                        found.append(label[:100])
                elif key == "screenshots" and isinstance(item, list):
                    for image in item[:6]:
                        if isinstance(image, str):
                            visit({"screenshot_path": image}, depth + 1)
                elif isinstance(item, dict):
                    visit(item, depth + 1)

    visit(result)
    return found
