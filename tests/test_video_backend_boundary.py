"""Film backend dependency and retired-product API guardrails.

Static source checks complement real HTTP security tests: no import of the
removed business adapters from actively dispatched Owner routes or Film media.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VideoBackendBoundaryTests(unittest.TestCase):
    def test_active_owner_api_imports_no_retired_product_modules(self):
        paths = (
            "agentforge/api/routes/bootstrap.py",
            "agentforge/api/routes/read.py",
            "agentforge/api/routes/media.py",
            "agentforge/api/routes/artifacts.py",
            "agentforge/api/routes/publishing.py",
        )
        forbidden = (
            "from agentforge.features.websites ",
            "from agentforge.features.websites import",
            "from agentforge.features.growth ",
            "from agentforge.features.growth import",
            "from agentforge import product_builder",
            "from agentforge import media_workflow_v15",
            "from agentforge import growth_store",
            "from agentforge import growth_reports",
            "from agentforge import quality_v14",
        )
        for relative in paths:
            content = (ROOT / relative).read_text(encoding="utf-8")
            for reference in forbidden:
                with self.subTest(module=relative, import_name=reference):
                    self.assertNotIn(reference, content)

    def test_canonical_image_and_publishing_do_not_import_business_domains(self):
        for relative in (
            "agentforge/features/media/comfy_image.py",
            "agentforge/features/media/visual_jobs.py",
            "agentforge/features/film_studio/publishing.py",
        ):
            content = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(module=relative):
                self.assertNotIn("from agentforge.features.websites", content)
                self.assertNotIn("from agentforge.features.growth", content)
                self.assertNotIn("from agentforge import product_builder", content)

    def test_model_hub_hides_retired_business_routing(self):
        text = (ROOT / "config/task_routes.toml").read_text(encoding="utf-8")
        for route in ("web.create", "webapp.architect", "webapp.develop",
                      "webapp.review", "growth.report", "media.copy_draft"):
            with self.subTest(route=route):
                self.assertNotIn(f'[routes."{route}"]', text)

    def test_mattress_backend_source_is_retired(self):
        self.assertFalse((ROOT / "agentforge/features/mattress_sales").exists())


if __name__ == "__main__":
    unittest.main()
