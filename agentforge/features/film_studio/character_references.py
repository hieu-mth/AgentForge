"""Immutable, local-only reference packs. No inference, upload to providers or model binding."""
import base64
import binascii
import hashlib
import io
from datetime import datetime, timezone

from agentforge.features.film_studio import characters

ROLES = ("primary", "full_body", "alternate")
MAX_IMAGE_BYTES = 512 * 1024
MAX_PIXELS = 12_000_000
MAX_REVISIONS = 12


def _identifier(value):
    if not isinstance(value, str) or not characters._ID.fullmatch(value):
        raise ValueError("Invalid character ID")
    return value


def _revision(value, *, minimum=1):
    if type(value) is not int or not minimum <= value <= MAX_REVISIONS:
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
        raise ValueError("Invalid reference role or image size (maximum 512 KiB)")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid base64 reference image") from None
    if not 1 <= len(payload) <= MAX_IMAGE_BYTES:
        raise ValueError("Invalid reference image size (maximum 512 KiB)")
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


def save_pack(data, path=None):
    if not isinstance(data, dict) or set(data) != {
            "character_id", "expected_character_version", "expected_revision", "images"}:
        raise ValueError("Invalid reference pack fields")
    ident = _identifier(data["character_id"])
    expected = _revision(data["expected_revision"], minimum=0)
    version = data["expected_character_version"]
    if type(version) is not int or version < 1:
        raise ValueError("Expected character version required")
    images = data["images"]
    if not isinstance(images, list) or not 1 <= len(images) <= len(ROLES):
        raise ValueError("Supply one to three reference images")
    decoded = [_image(entry) for entry in images]
    roles = [entry[0] for entry in decoded]
    if "primary" not in roles or len(set(roles)) != len(roles):
        raise ValueError("Primary reference required; roles must be unique")
    with characters._LOCK, characters._db(path, create=True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if _require_character(conn, ident) != version:
            raise ValueError("Character changed; refresh before saving references")
        conn.execute("""CREATE TABLE IF NOT EXISTS character_references (
            character_id TEXT NOT NULL, revision INTEGER NOT NULL, character_version INTEGER NOT NULL,
            role TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL,
            width INTEGER NOT NULL, height INTEGER NOT NULL, payload BLOB NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(character_id, revision, role))""")
        latest = conn.execute("SELECT COALESCE(MAX(revision),0) FROM character_references "
                              "WHERE character_id=?", (ident,)).fetchone()[0]
        if latest != expected:
            raise ValueError("Reference pack changed; refresh before saving")
        if latest >= MAX_REVISIONS:
            raise ValueError("Reference revision limit reached")
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany("INSERT INTO character_references VALUES (?,?,?,?,?,?,?,?,?,?)",
                         [(ident, latest+1, version, *entry, now) for entry in decoded])
        return _inventory(conn, ident, version)


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
