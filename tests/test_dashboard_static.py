"""The local Dashboard serves only allowlisted production assets."""
import unittest
from agentforge.api.static import _react_asset


class DashboardStaticTests(unittest.TestCase):
    def test_traversal_and_external_paths_are_rejected(self):
        for path in ("/dashboard/assets/../.env", "/dashboard/assets/a/b.js",
                     "/dashboard/src/App.jsx", "/.env", "/dashboard/assets/a.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                _react_asset(path)


if __name__ == "__main__":
    unittest.main()
