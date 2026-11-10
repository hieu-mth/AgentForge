"""Owner-authenticated local publishing actions. Never calls YouTube API."""
from agentforge.api.routes._shared import UNHANDLED
from agentforge.features.film_studio import production, publishing


def handle(server, path, request, session=None):
    if path == "/api/publishing/prepare":
        expected = {"ack", "film_slug", "episode_id", "episode_sha",
                    "render_sha", "metadata"}
        if set(request) != expected or request["ack"] != "PREPARE_PRIVATE_RELEASE":
            raise PermissionError("Explicit signed film release preparation required")
        key = request["film_slug"] + ":" + request["episode_id"]
        if (session is None or
                session.get("reviewed_film_productions", {}).get(key)
                != request["episode_sha"]):
            raise PermissionError("Inspect signed film episode before preparing a release")
        return publishing.prepare(
            film_slug=request["film_slug"], episode_id=request["episode_id"],
            episode_sha=request["episode_sha"], render_sha=request["render_sha"],
            metadata=request["metadata"], confirmed=True,
            growth_db_path=server.growth_db_path)
    if path.startswith("/api/publishing/") and path.endswith("/attest"):
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid release action")
        release_id = parts[3]
        if (set(request) != {"ack", "release_sha", "video_id", "privacy",
                             "owner_changed_on_youtube"}
                or request.get("ack") != "ATTEST_YOUTUBE_STUDIO_STATE"
                or request["owner_changed_on_youtube"] is not True):
            raise PermissionError("Manual platform-state attestation required")
        if (session is None or session.get("reviewed_publishing", {}).get(release_id)
                != request["release_sha"]):
            raise PermissionError("Inspect exact release SHA in this session")
        return publishing.owner_attest(
            release_id, request["release_sha"], request["video_id"],
            request["privacy"], confirmed=True)
    if path.startswith("/api/publishing/") and path.endswith("/observe"):
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid release action")
        release_id = parts[3]
        if (set(request) != {"ack", "release_sha", "snapshot", "owner_observed"}
                or request.get("ack") != "RECORD_OWNER_YOUTUBE_METRICS"
                or request["owner_observed"] is not True):
            raise PermissionError("Explicit Owner observation required")
        if (session is None or session.get("reviewed_publishing", {}).get(release_id)
                != request["release_sha"]):
            raise PermissionError("Inspect exact release SHA first")
        return publishing.observe(
            release_id, request["release_sha"], request["snapshot"], confirmed=True)
    return UNHANDLED
