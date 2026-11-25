"""Real image parsing, immutable pack revisions and read-only access."""
import base64
import hashlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agentforge.features.film_studio import character_references as refs, characters


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("media extra not installed")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "characters.db"
        self.character = characters.save_character({"name": "Mèo"}, self.db)
        self.ident = self.character["id"]
        output = io.BytesIO()
        Image.new("RGB", (32, 24), "orange").save(output, "PNG")
        self.payload = output.getvalue()

    def request(self, revision=0, version=1, images=None):
        if images is None:
            images = [{"role": "primary", "data_base64": base64.b64encode(self.payload).decode("ascii")}]
        return {"character_id": self.ident, "expected_character_version": version,
                "expected_revision": revision, "images": images}

    def test_read_does_not_create_reference_table(self):
        self.assertEqual(refs.list_packs(self.ident, self.db)["packs"], [])
        with sqlite3.connect(self.db) as conn:
            self.assertFalse(refs._table_exists(conn))

    def test_immutable_revisions_and_hash_checked_previews(self):
        first = refs.save_pack(self.request(), self.db)
        self.assertEqual(first["latest_revision"], 1)
        image = first["packs"][0]["images"][0]
        self.assertEqual(image["sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertNotIn("payload", image)
        self.assertEqual(refs.image_bytes(self.ident, 1, "primary", self.db), (self.payload, "image/png"))
        with self.assertRaisesRegex(ValueError, "Reference pack changed"):
            refs.save_pack(self.request(), self.db)
        second = refs.save_pack(self.request(1), self.db)
        self.assertEqual([p["revision"] for p in second["packs"]], [2, 1])
        self.assertEqual(second["packs"][1], first["packs"][0])
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE character_references SET payload=? WHERE revision=1", (b"tampered",))
        with self.assertRaisesRegex(ValueError, "integrity"):
            refs.image_bytes(self.ident, 1, "primary", self.db)

    def test_rejects_invalid_assets_and_stale_character(self):
        for images in (
            [{"role": "primary", "data_base64": "not base64"}],
            [{"role": "primary", "data_base64": base64.b64encode(b"<svg/>").decode()}],
            [{"role": "alternate", "data_base64": base64.b64encode(self.payload).decode()}],
        ):
            with self.subTest(images=images), self.assertRaises(ValueError):
                refs.save_pack(self.request(images=images), self.db)
        characters.save_character({"id": self.ident, "expected_version": 1, "name": "Mèo mới"}, self.db)
        with self.assertRaisesRegex(ValueError, "Character changed"):
            refs.save_pack(self.request(), self.db)
        self.assertEqual(refs.list_packs(self.ident, self.db)["packs"], [])
