"""Read-only unified Video Studio projection over existing production stores.

Film Studio is the canonical target for new productions. Historical V1.5
media productions remain visible but are never silently migrated or executed.
No external actions, state writes or model calls occur here.
"""


def list_projects(*, film_root=None, legacy_db_path=None, limit=16):
    from agentforge.features.film_studio import production
    from agentforge.features.media import workflow

    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("Invalid project limit")
    options = {"limit": limit}
    if film_root is not None:
        options["film_root"] = film_root
    episodes = production.list_episodes(**options)
    legacy_options = {}
    if legacy_db_path is not None:
        legacy_options["db_path"] = legacy_db_path
    historical = workflow.report(**legacy_options)["productions"]

    projects = [
        {
            "project_id": "film:" + row["film_slug"] + ":" + row["episode_id"],
            "source": "film_studio",
            "film_slug": row["film_slug"],
            "episode_id": row["episode_id"],
            "state": row["state"],
            "legacy_read_only": False,
            "visual_continuity_verified": False,
        }
        for row in episodes
    ]
    projects.extend(
        {
            "project_id": "legacy:" + row["production_id"],
            "source": "media_workflow_v15",
            "legacy_production_id": row["production_id"],
            "state": row["status"],
            "legacy_read_only": True,
            "visual_continuity_verified": False,
        }
        for row in historical[:limit]
    )
    return {
        "projects": projects,
        "canonical_engine": "film_studio",
        "legacy_write_enabled": False,
        "auto_publish": False,
        "runtime_certified": False,
    }
