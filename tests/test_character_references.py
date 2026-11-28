"""Real image parsing, immutable pack revisions and read-only access."""
import base64
import hashlib
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
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
        with closing(sqlite3.connect(self.db)) as conn, conn:
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
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE character_references SET payload=? WHERE revision=1", (b"tampered",))
        with self.assertRaisesRegex(ValueError, "integrity"):
            refs.image_bytes(self.ident, 1, "primary", self.db)

    def test_atomic_character_and_multiview_pack(self):
        encoded = base64.b64encode(self.payload).decode("ascii")
        images = [{"role": role, "data_base64": encoded} for role in refs.ROLES]
        result = refs.save_character_with_pack(
            {"name": "Mực", "appearance": "Mèo đen"},
            {"expected_revision": 0, "images": images, "keep_roles": []}, self.db)
        character = result["character"]
        ident = character["id"]
        pack = refs.list_packs(ident, self.db)["packs"][0]
        self.assertEqual({image["role"] for image in pack["images"]}, set(refs.ROLES))
        self.assertEqual(pack["character_version"], character["version"])
        inventory = refs.library(self.db)["characters"]
        row = next(row for row in inventory if row["id"] == ident)
        self.assertEqual(row["reference_pack"]["revision"], 1)
        self.assertTrue(row["reference_pack"]["preview_url"].endswith("/1/primary"))
        result = refs.save_character_with_pack(
            {"id": ident, "expected_version": 1, "name": "Mực mới"},
            {"expected_revision": 1, "images": [], "keep_roles": ["primary", "sheet"]}, self.db)
        self.assertEqual(result["character"]["version"], 2)
        packs = refs.list_packs(ident, self.db)["packs"]
        self.assertEqual({image["role"] for image in packs[0]["images"]}, {"primary", "sheet"})
        self.assertEqual(packs[1], pack)
        with self.assertRaisesRegex(ValueError, "Reference pack changed"):
            refs.save_character_with_pack(
                {"id": ident, "expected_version": 2, "name": "Sai"},
                {"expected_revision": 1, "images": images, "keep_roles": []}, self.db)
        self.assertEqual(next(row for row in characters.list_characters(self.db)["characters"]
                              if row["id"] == ident)["name"], "Mực mới")
        self.assertEqual(refs.list_packs(ident, self.db)["latest_revision"], 2)
        with self.assertRaisesRegex(ValueError, "Primary reference required"):
            refs.save_character_with_pack(
                {"name": "No primary"},
                {"expected_revision": 0, "images": [images[-1]], "keep_roles": []}, self.db)
        self.assertNotIn("No primary", [row["name"] for row in characters.list_characters(self.db)["characters"]])

    def test_archive_keeps_pinned_reference_readable(self):
        refs.save_pack(self.request(), self.db)
        characters.set_archived(self.ident, 1, True, self.db)
        self.assertEqual(characters.list_characters(self.db)["characters"], [])
        row = refs.library(self.db)["characters"][0]
        self.assertTrue(row["archived"])
        self.assertEqual(refs.image_bytes(self.ident, 1, "primary", self.db)[0], self.payload)
        with self.assertRaises(ValueError):
            characters.set_archived(self.ident, 1, False, self.db)
        characters.set_archived(self.ident, row["version"], False, self.db)
        self.assertEqual(characters.list_characters(self.db)["characters"][0]["id"], self.ident)
        self.assertEqual(refs.list_packs(self.ident, self.db)["latest_revision"], 1)

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
