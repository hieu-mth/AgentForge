"""Read-only project inventory for current Studio drafts and manual film episodes."""


def list_projects(*, film_root=None, limit=16):
    from agentforge.features.film_studio import production, draft_pipeline

    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("Invalid project limit")
    options = {"limit": limit}
    if film_root is not None:
        options["film_root"] = film_root
    episodes = production.list_episodes(**options)
    drafts = draft_pipeline.list_drafts()
    studio = [{"project_id": "draft:" + job["id"], "source": "studio_draft",
               "film_slug": job.get("board", {}).get("title") or job["id"],
               "episode_id": "v" + str(job.get("storyboard_version", 1)),
               "state": job["status"], "draft_id": job["id"],
               "visual_continuity_verified": False} for job in drafts]
    manual = [{"project_id": "film:" + row["film_slug"] + ":" + row["episode_id"],
               "source": "film_studio", "film_slug": row["film_slug"],
               "episode_id": row["episode_id"], "state": row["state"],
               "visual_continuity_verified": False} for row in episodes]
    return {"projects": (studio + manual)[:limit], "canonical_engine": "film_studio",
            "auto_publish": False, "runtime_certified": False}
