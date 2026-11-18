"""Canonical Film Studio project inventory.

Only film productions are exposed. Legacy media V1.5 is not imported,
migrated, or executed. Owner files are never deleted by this module.
"""


def list_projects(*, film_root=None, limit=16):
    from agentforge.features.film_studio import production

    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("Invalid project limit")
    options = {"limit": limit}
    if film_root is not None:
        options["film_root"] = film_root
    episodes = production.list_episodes(**options)
    return {
        "projects": [
            {
                "project_id": "film:" + row["film_slug"] + ":" + row["episode_id"],
                "source": "film_studio",
                "film_slug": row["film_slug"],
                "episode_id": row["episode_id"],
                "state": row["state"],
                "visual_continuity_verified": False,
            }
            for row in episodes
        ],
        "canonical_engine": "film_studio",
        "auto_publish": False,
        "runtime_certified": False,
    }
