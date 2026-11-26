"""Pure worker-attempt state transitions; persistence and locks belong to the caller."""


def begin_attempt(job, now):
    job.update(status="RUNNING", error=None, attempt_started_at=now)
    job.setdefault("started_at", now)
    for key in ("error_code", "attempt_finished_at", "failed_scene", "activity"):
        job.pop(key, None)


def finish_attempt(job, now, *, cancelled):
    activity = job.pop("activity", {})
    if job["status"] == "FAILED" and activity.get("scene"):
        job["failed_scene"] = activity["scene"]
    # Cancellation cannot hide a provider job with an ambiguous outcome.
    if job["status"] != "NEEDS_RECONCILIATION" and cancelled:
        job.update(status="CANCELLED", error=None, video_sha=None)
    if job.get("attempt_started_at"):
        job["attempt_finished_at"] = now


def interrupted_view(job, active_id):
    job["worker_active"] = job["id"] == active_id
    if job["status"] == "RUNNING" and not job["worker_active"] and "storyboard_version" in job:
        job["status"] = "INTERRUPTED"
    return job
