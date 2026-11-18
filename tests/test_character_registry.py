"""Character registry tests: persistence, version safety and validation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agentforge.paths import REPOSITORY_ROOT
from agentforge.features.film_studio import characters as registry
from agentforge.features.film_studio.characters import list_characters, save_character

class CharacterRegistryTests(unittest.TestCase):
    def test_create_update_and_stale_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"characters.db"
            self.assertEqual(list_characters(db)["characters"], [])
            first=save_character({"name":"Mèo Mun","species":"mèo","personality":"ham ăn"},db)
            self.assertEqual(first["version"],1)
            self.assertEqual(len(list_characters(db)["characters"]),1)
            second=save_character({"id":first["id"],"expected_version":1,
                "name":"Mèo Mun","species":"mèo","personality":"thích ngủ"},db)
            self.assertEqual(second["version"],2)
            with self.assertRaises(ValueError):
                save_character({"id":first["id"],"expected_version":1,"name":"Sai"},db)
            self.assertEqual(list_characters(db)["characters"][0]["personality"],"thích ngủ")
    def test_read_only_get_does_not_create_database_or_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nested" / "missing.sqlite3"
            self.assertEqual(list_characters(db), {"characters": []})
            self.assertFalse(db.exists())
            self.assertFalse(db.parent.exists())

    def test_default_db_ignores_process_working_directory(self):
        with patch.dict("os.environ", {"AGENTFORGE_CHARACTER_DB": "data/characters.sqlite3"}):
            self.assertEqual(registry._db_path(),
                             REPOSITORY_ROOT / "data" / "characters.sqlite3")

    def test_rejects_symlink_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "storage"
            real.mkdir()
            alias = root / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable")
            with self.assertRaises(PermissionError):
                list_characters(alias / "characters.sqlite3")
            with self.assertRaises(PermissionError):
                save_character({"name": "No linked storage"}, alias / "characters.sqlite3")
            self.assertFalse((real / "characters.sqlite3").exists())

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"characters.db"
            for bad in ({},{"name":""},{"name":"x"*101},{"name":123},
                        {"name":"OK","appearance":123}):
                with self.assertRaises(ValueError):
                    save_character(bad,db)

if __name__=="__main__":
    unittest.main()
