"""Immutable, local-only reference packs. No inference, upload to providers or model binding."""
import base64
import binascii
import hashlib
import io
from datetime import datetime, timezone

from agentforge.features.film_studio import characters

ROLES = ("primary", "full_body", "alternate", "left", "right", "rear", "sheet")
MAX_IMAGE_BYTES = 1024 * 1024
MAX_PIXELS = 12_000_000


def _identifier(value):
    if not isinstance(value, str) or not characters._ID.fullmatch(value):
        raise ValueError("Invalid character ID")
    return value


def _revision(value, *, minimum=1):
    if type(value) is not int or not minimum <= value <= 2**63-1:
        raise ValueError("Invalid reference revision")
    return value


def _require_character(conn, ident):
    if conn is None:
        raise KeyError("Character not found")
    row = conn.execute("SELECT version FROM characters WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise KeyError("Character not found")
    return row["version"]


def _table_exists(conn):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_references'"
    ).fetchone())


def _image(entry):
    if not isinstance(entry, dict) or set(entry) != {"role", "data_base64"}:
        raise ValueError("Invalid reference image fields")
    role, encoded = entry["role"], entry["data_base64"]
    if role not in ROLES or not isinstance(encoded, str) or len(encoded) > 4*((MAX_IMAGE_BYTES+2)//3):
        raise ValueError("Invalid reference role or image size (maximum 1 MiB)")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid base64 reference image") from None
    if not 1 <= len(payload) <= MAX_IMAGE_BYTES:
        raise ValueError("Invalid reference image size (maximum 1 MiB)")
    try:
        from PIL import Image
    except ImportError:
        raise ValueError("Install AgentForge with the media extra to import reference images") from None
    try:
        with Image.open(io.BytesIO(payload)) as image:
            if (image.format not in {"PNG", "JPEG"} or image.width * image.height > MAX_PIXELS
                    or getattr(image, "n_frames", 1) != 1):
                raise ValueError("Only still PNG/JPEG reference images up to 12 megapixels")
            mime = "image/png" if image.format == "PNG" else "image/jpeg"
            width, height = image.size
            image.verify()
        # Verify pixel decoding as well as file structure.
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("Invalid or damaged reference image") from None
    return (role, hashlib.sha256(payload).hexdigest(), mime, width, height, payload)


def _inventory(conn, ident, version):
    packs = []
    if _table_exists(conn):
        rows = conn.execute("""SELECT revision, character_version, role, sha256, mime,
            width, height, length(payload) AS size_bytes, created_at FROM character_references
            WHERE character_id=? ORDER BY revision DESC, role""", (ident,))
        for row in rows:
            item = dict(row)
            revision = item.pop("revision")
            character_version = item.pop("character_version")
            created_at = item.pop("created_at")
            if not packs or packs[-1]["revision"] != revision:
                packs.append({"revision": revision, "character_version": character_version,
                              "created_at": created_at, "images": []})
            item["preview_url"] = f"/api/characters/{ident}/references/{revision}/{item['role']}"
            packs[-1]["images"].append(item)
    return {"character_id": ident, "character_version": version,
            "latest_revision": packs[0]["revision"] if packs else 0, "packs": packs}


def list_packs(ident, path=None):
    ident = _identifier(ident)
    with characters._LOCK, characters._db(path) as conn:
        version = _require_character(conn, ident)
        return _inventory(conn, ident, version)


def _decode_pack(images):
    if not isinstance(images, list) or not 1 <= len(images) <= len(ROLES):
        raise ValueError("Supply one to seven reference images")
    decoded = [_image(entry) for entry in images]
    roles = [entry[0] for entry in decoded]
    if len(set(roles)) != len(roles):
        raise ValueError("Reference roles must be unique")
    return decoded


def _insert_pack(conn, ident, version, expected, decoded, keep_roles=()):
    conn.execute("""CREATE TABLE IF NOT EXISTS character_references (
        character_id TEXT NOT NULL, revision INTEGER NOT NULL, character_version INTEGER NOT NULL,
        role TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL,
        width INTEGER NOT NULL, height INTEGER NOT NULL, payload BLOB NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(character_id, revision, role))""")
    latest = conn.execute("SELECT COALESCE(MAX(revision),0) FROM character_references "
                          "WHERE character_id=?", (ident,)).fetchone()[0]
    if latest != expected:
        raise ValueError("Reference pack changed; refresh before saving")
    entries = {entry[0]: entry for entry in decoded}
    for role in keep_roles:
        if role in entries:
            raise ValueError("Reference role cannot be retained and replaced")
        row = conn.execute("SELECT role,sha256,mime,width,height,payload FROM character_references "
                           "WHERE character_id=? AND revision=? AND role=?", (ident, latest, role)).fetchone()
        if row is None or hashlib.sha256(row["payload"]).hexdigest() != row["sha256"]:
            raise ValueError("Retained reference missing or damaged")
        entries[role] = tuple(row)
    if "primary" not in entries:
        raise ValueError("Primary reference required")
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany("INSERT INTO character_references VALUES (?,?,?,?,?,?,?,?,?,?)",
                     [(ident, latest+1, version, *entry, now) for entry in entries.values()])
    return _inventory(conn, ident, version)


def save_pack(data, path=None):
    if not isinstance(data, dict) or set(data) != {
            "character_id", "expected_character_version", "expected_revision", "images"}:
        raise ValueError("Invalid reference pack fields")
    ident = _identifier(data["character_id"])
    expected = _revision(data["expected_revision"], minimum=0)
    version = data["expected_character_version"]
    if type(version) is not int or version < 1:
        raise ValueError("Expected character version required")
    decoded = _decode_pack(data["images"])
    with characters._LOCK, characters._db(path, create=True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if _require_character(conn, ident) != version:
            raise ValueError("Character changed; refresh before saving references")
        if characters._archive_exists(conn) and conn.execute(
                "SELECT 1 FROM character_archives WHERE character_id=?", (ident,)).fetchone():
            raise ValueError("Restore archived character before editing")
        return _insert_pack(conn, ident, version, expected, decoded)


def save_character_with_pack(data, pack=None, path=None):
    """One transaction for metadata and a new owner-selected reference revision."""
    values = characters._validate(data)
    if pack is not None:
        if not isinstance(pack, dict) or set(pack) != {"expected_revision", "images", "keep_roles"}:
            raise ValueError("Invalid reference pack fields")
        expected = _revision(pack["expected_revision"], minimum=0)
        keep = pack["keep_roles"]
        if (not isinstance(keep, list) or any(role not in ROLES for role in keep)
                or len(set(keep)) != len(keep)):
            raise ValueError("Invalid retained reference roles")
        decoded = _decode_pack(pack["images"]) if pack["images"] != [] else []
    with characters._LOCK, characters._db(path, create=True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        character = characters._save_record(conn, data, values)
        if pack is not None:
            _insert_pack(conn, character["id"], character["version"], expected, decoded, keep)
        return {"character": character}


def library(path=None):
    """Read-only inventory with current reference thumbnail and coverage."""
    with characters._LOCK:
        result = characters.list_characters(path, include_archived=True)
        with characters._db(path) as conn:
            if conn is None or not _table_exists(conn):
                return result
            rows = conn.execute("""SELECT r.character_id,r.revision,r.role,r.character_version
                FROM character_references r JOIN
                (SELECT character_id,MAX(revision) AS latest FROM character_references GROUP BY character_id) p
                ON r.character_id=p.character_id AND r.revision=p.latest""")
            packs = {}
            for row in rows:
                item = packs.setdefault(row["character_id"], {"revision": row["revision"],
                    "character_version": row["character_version"], "roles": []})
                item["roles"].append(row["role"])
            for character in result["characters"]:
                pack = packs.get(character["id"])
                if pack:
                    pack["preview_url"] = f"/api/characters/{character['id']}/references/{pack['revision']}/primary"
                    character["reference_pack"] = pack
        return result


def image_bytes(ident, revision, role, path=None):
    ident = _identifier(ident)
    revision = _revision(revision)
    if role not in ROLES:
        raise ValueError("Invalid reference role")
    with characters._LOCK, characters._db(path) as conn:
        _require_character(conn, ident)
        if not _table_exists(conn):
            raise KeyError("Reference not found")
        row = conn.execute("SELECT sha256,mime,payload FROM character_references "
                           "WHERE character_id=? AND revision=? AND role=?",
                           (ident, revision, role)).fetchone()
        if row is None:
            raise KeyError("Reference not found")
        payload = row["payload"]
        if (not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_IMAGE_BYTES
                or hashlib.sha256(payload).hexdigest() != row["sha256"]
                or row["mime"] not in {"image/png", "image/jpeg"}):
            raise ValueError("Reference image integrity check failed")
        return payload, row["mime"]


def analyze_primary(reference, *, allow_cloud):
    """One explicit advisory vision call; never mutate the character or its pack."""
    from contextlib import nullcontext
    from agentforge import ops_control
    from agentforge.ai import model_hub
    from agentforge.features.film_studio import studio_vision
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise ValueError("Install AgentForge with the media extra to analyze references") from None

    if not isinstance(reference, dict) or type(allow_cloud) is not bool:
        raise ValueError("Invalid character analysis request")
    if set(reference) == {"data_base64"}:
        payload = _image({"role": "primary", **reference})[-1]
    elif set(reference) == {"character_id", "revision"}:
        payload, _ = image_bytes(reference["character_id"], reference["revision"], "primary")
    else:
        raise ValueError("Supply one primary image or a saved reference")
    ops_control.require_active()
    revision, profile, limit = model_hub.vision_binding(require_ffmpeg=False)
    cloud = model_hub.is_cloud(profile)
    if cloud and (not allow_cloud or limit < 1):
        raise PermissionError("Cần xác nhận gửi ảnh và cho phép lượt gọi AI cloud.")
    # Only send a bounded JPEG of the subject; never send the original metadata.
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    sheet = None
    for size in (768, 512, 384):
        image.thumbnail((size, size))
        for quality in (85, 65, 45):
            output = io.BytesIO()
            image.save(output, "JPEG", quality=quality)
            if len(output.getvalue()) <= studio_vision.MAX_SHEET_BYTES:
                sheet = output.getvalue()
                break
        if sheet is not None:
            break
    if sheet is None:
        raise ValueError("Cannot prepare bounded reference image")
    with (nullcontext() if cloud else model_hub.local_inference_slot()):
        with model_hub.media_probe_dispatch(profile, revision):
            result = studio_vision.describe_identity(profile, sheet)
    return {**result, "model_id": profile["id"], "scope": "PRIMARY_IMAGE_ADVISORY"}
