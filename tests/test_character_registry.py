"""Character registry tests: persistence, version safety and validation."""
import tempfile
import unittest
from pathlib import Path
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
    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"characters.db"
            for bad in ({},{"name":""},{"name":"x"*101},{"name":123},
                        {"name":"OK","appearance":123}):
                with self.assertRaises(ValueError):
                    save_character(bad,db)

if __name__=="__main__":
    unittest.main()
