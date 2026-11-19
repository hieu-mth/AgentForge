"""Serve only the verified local episode master to an authenticated Owner."""
import os
import re
import stat

from agentforge.features.film_studio import motion_comfy, motion_verify, production
from agentforge.paths import ensure_local_root

RANGE = re.compile(r"bytes=([0-9]{0,12})-([0-9]{0,12})\Z")


def _range(header, size):
    if header is None:
        return 0, size - 1, 200
    match = RANGE.fullmatch(header)
    if not match:
        raise ValueError("Invalid byte range")
    left, right = match.groups()
    if left:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
        if start <= end:
            return start, end, 206
    elif right and int(right) > 0:
        return max(0, size - int(right)), size - 1, 206
    raise ValueError("Unsatisfiable byte range")


def preview(handler, film, episode):
    try:
        folder = production._folder(film, episode, production.FILMS)
        path = folder / "episode.mp4"
    except (ValueError, OSError):
        return handler._blocked(404, "film_preview_unavailable")
    return _serve(handler, path, production.MAX_OUTPUT_BYTES, "episode.mp4",
                  lambda stream: production.inspect_render(
                      episode, film, film_root=production.FILMS, video_stream=stream))


def clip_preview(handler, job_id):
    try:
        root, db = motion_comfy.FILMS, motion_comfy.DB
        row = motion_verify._job(job_id, db)
        if row["state"] != "COMPLETE_UNVERIFIED":
            return handler._blocked(404, "film_preview_unavailable")
        path = motion_verify._dir(row, root) / "clip.mp4"
    except (ValueError, OSError, KeyError):
        return handler._blocked(404, "film_preview_unavailable")
    return _serve(handler, path, motion_verify.MAX_MP4_BYTES, "clip.mp4",
                  lambda stream: motion_verify.inspect_receipt(
                      job_id, film_root=root, db_path=db, video_stream=stream))


def _serve(handler, path, max_size, filename, verify):
    try:
        path = ensure_local_root(path)
        if not path.is_file():
            return handler._blocked(404, "film_preview_unavailable")
        stream = path.open("rb")
    except (ValueError, OSError):
        return handler._blocked(404, "film_preview_unavailable")

    with stream:
        try:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or
                    not production.MIN_MP4 <= before.st_size <= max_size):
                return handler._blocked(404, "film_preview_unavailable")
            size = before.st_size
            verify(stream)
            try:
                start, end, status = _range(handler.headers.get("Range"), size)
            except ValueError:
                return handler._reply(416, b"", mime="video/mp4", headers=(
                    ("Content-Range", f"bytes */{size}"),))
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                return handler._blocked(404, "film_preview_unavailable")
            stream.seek(start)
        except (ValueError, OSError, KeyError):
            return handler._blocked(404, "film_preview_unavailable")

        headers = [("Accept-Ranges", "bytes"),
                   ("Content-Disposition", f'inline; filename="{filename}"')]
        if status == 206:
            headers.append(("Content-Range", f"bytes {start}-{end}/{size}"))
        remaining = end - start + 1
        try:
            handler._reply_headers(status, "video/mp4", remaining, headers)
            while remaining:
                chunk = stream.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
        except OSError:
            # The client may cancel one range when seeking to another.
            pass
