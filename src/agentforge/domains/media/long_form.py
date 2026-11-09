"""Deterministic long-form film *planning*, without video inference or publishing.

Each shot is a separately addressable placeholder that must receive original
storyboarding, reference assets, generated motion and QA before editing. A film
plan is not a video; do not treat PLANNED_NOT_RENDERED as successful production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

FORMAT = "agentforge.film.plan.v1"
MAX_RUNTIME_SECONDS = 6 * 60 * 60
MAX_SHOTS = 3000
MAX_CHAPTERS = 200
ID = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")


class FilmPlanError(ValueError):
    """Invalid film plan or stale/tampered plan file."""


def _text(value: str, label: str, limit: int) -> str:
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= limit
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise FilmPlanError(f"Invalid {label}")
    return value.strip()


def _id(value: str, label: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise FilmPlanError(f"Invalid {label}")
    return value


def _int(value: int, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise FilmPlanError(f"Invalid {label}")
    return value


def _digest(body: dict) -> str:
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_plan(*, title: str, genre: str, style: str,
               chapters: list[dict], characters: list[dict] | None = None,
               shot_seconds: int = 8) -> dict:
    """Expand bounded chapter beats into individually editable shot *slots*.

    No motion prompts are invented and no provider, subprocess or API is called.
    A chapter supplies a narrative goal, not 100 identical shot prompts.
    """
    title = _text(title, "title", 140)
    genre = _text(genre, "genre", 80)
    style = _text(style, "style", 600)
    shot_seconds = _int(shot_seconds, "shot_seconds", 4, 15)
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= MAX_CHAPTERS:
        raise FilmPlanError("Expected 1–200 chapters")
    if characters is None:
        characters = []
    if not isinstance(characters, list) or len(characters) > 80:
        raise FilmPlanError("Expected at most 80 characters")
    cast, cast_ids = [], set()
    for char in characters:
        if not isinstance(char, dict) or set(char) != {"id", "name", "visual_bible", "voice_notes"}:
            raise FilmPlanError("Invalid character bible entry")
        ident = _id(char["id"], "character id")
        if ident in cast_ids:
            raise FilmPlanError("Duplicate character id")
        cast_ids.add(ident)
        cast.append({"id": ident,
                     "name": _text(char["name"], "character name", 100),
                     "visual_bible": _text(char["visual_bible"], "character visual bible", 1200),
                     "voice_notes": _text(char["voice_notes"], "character voice notes", 350)})

    film_chapters, shots = [], []
    chapter_ids, start = set(), 0
    for chap in chapters:
        if not isinstance(chap, dict) or set(chap) != {"id", "title", "synopsis", "duration_seconds", "character_ids"}:
            raise FilmPlanError("Invalid chapter")
        cid = _id(chap["id"], "chapter id")
        if cid in chapter_ids:
            raise FilmPlanError("Duplicate chapter id")
        chapter_ids.add(cid)
        seconds = _int(chap["duration_seconds"], "chapter duration", 4, MAX_RUNTIME_SECONDS)
        assigned = chap["character_ids"]
        if (not isinstance(assigned, list) or len(assigned) != len(set(map(str, assigned)))
                or any(not isinstance(x, str) or x not in cast_ids for x in assigned)):
            raise FilmPlanError("Chapter references unknown/duplicate character")
        film_chapters.append({"id": cid,
                              "title": _text(chap["title"], "chapter title", 140),
                              "synopsis": _text(chap["synopsis"], "chapter synopsis", 3000),
                              "duration_seconds": seconds,
                              "start_seconds": start,
                              "character_ids": list(assigned)})
        for local in range(0, seconds, shot_seconds):
            duration = min(shot_seconds, seconds - local)
            shots.append({"shot_id": f"sh-{len(shots)+1:05d}", "chapter_id": cid,
                          "start_seconds": start + local,
                          "duration_seconds": duration,
                          "status": "NEEDS_STORYBOARD",
                          "motion_prompt": None, "reference_asset_sha256": None,
                          "generated_video_sha256": None})
            if len(shots) > MAX_SHOTS:
                raise FilmPlanError("Film exceeds maximum shot budget")
        start += seconds
        if start > MAX_RUNTIME_SECONDS:
            raise FilmPlanError("Film exceeds six hours")

    body = {"format": FORMAT, "title": title, "genre": genre,
            "style": style, "runtime_seconds": start,
            "shot_target_seconds": shot_seconds,
            "characters": cast, "chapters": film_chapters, "shots": shots,
            "status": "PLANNED_NOT_RENDERED", "runtime_verified": False,
            "youtube_uploaded": False}
    return {**body, "plan_sha256": _digest(body)}


def verify_plan(document: dict) -> dict:
    """Verify that the stored plan is intact and still only a plan."""
    if not isinstance(document, dict) or not isinstance(document.get("plan_sha256"), str):
        raise FilmPlanError("Invalid plan document")
    checksum = document["plan_sha256"]
    body = {k: v for k, v in document.items() if k != "plan_sha256"}
    if (not re.fullmatch(r"[a-f0-9]{64}", checksum) or _digest(body) != checksum
            or body.get("format") != FORMAT or body.get("status") != "PLANNED_NOT_RENDERED"
            or body.get("runtime_verified") is not False
            or body.get("youtube_uploaded") is not False):
        raise FilmPlanError("Film plan SHA mismatch or invalid state")
    try:
        expected = build_plan(
            title=body["title"], genre=body["genre"], style=body["style"],
            chapters=[{k: x[k] for k in ("id", "title", "synopsis", "duration_seconds", "character_ids")}
                      for x in body["chapters"]],
            characters=body["characters"], shot_seconds=body["shot_target_seconds"])
    except (KeyError, TypeError, FilmPlanError) as exc:
        raise FilmPlanError("Invalid stored film plan structure") from exc
    if expected != document:
        raise FilmPlanError("Film plan structure is not canonical")
    return document


def estimate_attempts(plan: dict, *, attempts_per_shot: int = 2) -> dict:
    """An effort estimate, not a cost/performance promise."""
    verify_plan(plan)
    attempts = _int(attempts_per_shot, "attempts_per_shot", 1, 20)
    return {"shots": len(plan["shots"]),
            "estimated_generation_attempts": len(plan["shots"]) * attempts,
            "total_output_seconds": plan["runtime_seconds"],
            "estimated_money": None, "estimated_gpu_hours": None,
            "quality_verified": False}


def save_plan(root: Path, slug: str, plan: dict) -> Path:
    """Exclusive local save. Never overwrite an existing production or plan."""
    verify_plan(plan)
    slug = _id(slug, "film slug")
    root = Path(root)
    if root.is_symlink() or (root / slug).is_symlink():
        raise FilmPlanError("Symlink film path is forbidden")
    folder = root / slug
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / "film-plan.json"
    if file.is_symlink():
        raise FilmPlanError("Symlink film plan is forbidden")
    with file.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2)
    return file


def load_plan(root: Path, slug: str) -> dict:
    slug = _id(slug, "film slug")
    root = Path(root)
    file = root / slug / "film-plan.json"
    if root.is_symlink() or (root / slug).is_symlink() or file.is_symlink():
        raise FilmPlanError("Symlink film path is forbidden")
    if not file.is_file() or file.stat().st_size > 3_000_000:
        raise FilmPlanError("Film plan missing or too large")
    try:
        return verify_plan(json.loads(file.read_text(encoding="utf-8")))
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise FilmPlanError("Malformed film plan") from exc


def main(argv: list[str] | None = None) -> None:
    """Offline CLI for shot-slot plans. Does NOT create a rendered movie."""
    parser = argparse.ArgumentParser(description="AgentForge offline long-form film plan (no video inference)")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("plan", help="Expand chapter spec into unrendered shot slots")
    create.add_argument("--spec", type=Path, required=True, help="Trusted authored JSON story specification")
    create.add_argument("--output-root", type=Path, required=True)
    create.add_argument("--slug", required=True)
    inspect = actions.add_parser("inspect", help="Validate saved film plan SHA and count shot slots")
    inspect.add_argument("--output-root", type=Path, required=True)
    inspect.add_argument("--slug", required=True)
    args = parser.parse_args(argv)
    if args.action == "plan":
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        if not isinstance(spec, dict) or set(spec) != {
                "title", "genre", "style", "chapters", "characters", "shot_seconds"}:
            parser.error("Spec requires exact title,genre,style,chapters,characters,shot_seconds")
        document = build_plan(**spec)
        output = save_plan(args.output_root, args.slug, document)
    else:
        document = load_plan(args.output_root, args.slug)
        output = args.output_root / args.slug / "film-plan.json"
    summary = {"path": str(output), "plan_sha256": document["plan_sha256"],
               "runtime_seconds": document["runtime_seconds"],
               "shot_count": len(document["shots"]),
               "status": document["status"], "video_rendered": False}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
