"""Optional explicit YouTube OAuth desktop private upload, never public posting.

This module is imported only on an Owner-executed CLI command. No credentials
or refresh tokens are serialized to AgentForge; the Google OAuth desktop flow
opens a local loopback browser and keeps credentials in process memory only.
Upload ambiguity is checkpointed before external videos.insert, never retried.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentforge import ops_control
from agentforge.features.film_studio import publishing, production
from agentforge.paths import REPOSITORY_ROOT, ensure_local_root

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
CHUNK = 8 * 1024 * 1024


def _outside_repo(path):
    target = ensure_local_root(Path(path).resolve(strict=True))
    if not target.is_file() or target.stat().st_size > 20_000:
        raise publishing.PublishingError("OAuth desktop client JSON must be a small local file")
    root = REPOSITORY_ROOT.resolve()
    if target == root or root in target.parents:
        raise publishing.PublishingError("Store OAuth client file outside the repository")
    return target


def _authorize(client_file):
    """One interactive localhost OAuth grant; no token cache or persisted secret."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError('Install explicit opt-in: pip install -e ".[youtube]"') from exc
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file), [SCOPE])
        credentials = flow.run_local_server(
            host="127.0.0.1", port=0, open_browser=True,
            authorization_prompt_message="Open this Owner OAuth URL in your local browser: {url}",
            success_message="YouTube private upload OAuth approved. Return to AgentForge.",
        )
        if credentials is None or not credentials.valid:
            raise RuntimeError("OAuth did not return valid Owner authorization")
        return credentials
    except Exception:
        # Do not expose full OAuth exception including authorization code/token.
        raise RuntimeError("YouTube OAuth failed; no video upload attempted") from None


def _dispatch(video_file, credentials, item):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError('Install explicit opt-in: pip install -e ".[youtube]"') from exc
    # Explicitly private, never platform schedule or public/unlisted.
    status = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": item["made_for_kids"],
        "containsSyntheticMedia": item["synthetic_media"],
    }
    body = {"snippet": {"title": item["title"], "description": item["description"],
                        "categoryId": "22"},
            "status": status}
    service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    request = service.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video_file), mimetype="video/mp4",
                                   chunksize=CHUNK, resumable=True))
    response = None
    while response is None:
        _, response = request.next_chunk()
    # A successful HTTP upload response is still not public publication proof.
    if (not isinstance(response, dict)
            or response.get("status", {}).get("privacyStatus") != "private"):
        raise RuntimeError("YouTube response did not confirm private-only upload")
    return response.get("id")


def upload_private(release_id, release_sha, *, client_secrets_path,
                   confirmed=False, db_path=publishing.DB,
                   film_root=production.FILMS):
    if confirmed is not True:
        raise PermissionError("Explicit Owner private-only YouTube upload required")
    ops_control.require_active()
    secret_file = _outside_repo(client_secrets_path)
    item = publishing.inspect(release_id, db_path=db_path, film_root=film_root)
    if release_sha != item["release_sha256"]:
        raise PermissionError("Release SHA changed since Owner review")
    if item["status"] != "READY_FOR_MANUAL_HANDOFF":
        raise PermissionError("Release already attempted; never blindly retry")
    handoff = publishing.handoff(release_id, db_path=db_path, film_root=film_root)
    video_file = Path(handoff["video_file"])
    # Reverify the exact Wave 9 render and source hash before any OAuth/network.
    report = production.inspect_render(
        item["episode_id"], item["film_slug"], film_root=film_root)
    if (report["video_sha256"] != item["video_sha256"]
            or report["receipt_sha256"] != item["render_receipt_sha256"]):
        raise PermissionError("Rendered MP4 receipt is stale")
    credentials = _authorize(secret_file)
    publishing.checkpoint_private_upload(
        release_id, release_sha, confirmed=True,
        db_path=db_path, film_root=film_root)
    try:
        video_id = _dispatch(video_file, credentials, item)
        # Re-hash *after* resumable upload, too. A local process may have
        # replaced the file while OAuth/upload was in progress. We must not
        # record a successful source-identical upload in that case. The API
        # may already have created a private video: leave status UNCERTAIN.
        after = production.inspect_render(
            item["episode_id"], item["film_slug"], film_root=film_root)
        if (after["video_sha256"] != item["video_sha256"]
                or after["receipt_sha256"] != item["render_receipt_sha256"]):
            raise PermissionError("Film source changed while uploading")
        publishing.complete_private_upload(
            release_id, release_sha, video_id, db_path=db_path)
    except Exception:
        # The API may have created the video already. Keep UNCERTAIN until
        # Owner checks YouTube Studio; never resubmit automatically.
        raise RuntimeError(
            "YOUTUBE_UPLOAD_UNCERTAIN: Inspect YouTube Studio manually; do not retry."
        ) from None
    return {
        "status": "PRIVATE_UPLOADED_API", "release_id": release_id,
        "youtube_video_id": video_id, "privacy_status": "private",
        "public_visibility_verified": False, "monetization_verified": False,
        "scheduled_publication": False, "credentials_saved": False,
    }


def main(argv=None):
    cli = argparse.ArgumentParser(
        description="One-shot Owner-controlled YouTube private upload, no auto publish")
    cmd = cli.add_subparsers(dest="action", required=True)
    publish = cmd.add_parser("upload-private")
    publish.add_argument("--release-id", required=True)
    publish.add_argument("--release-sha", required=True)
    publish.add_argument("--oauth-client-file", type=Path, required=True)
    publish.add_argument("--confirm-private-upload", action="store_true")
    args = cli.parse_args(argv)
    out = upload_private(
        args.release_id, args.release_sha,
        client_secrets_path=args.oauth_client_file,
        confirmed=args.confirm_private_upload)
    print(json.dumps(out, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
