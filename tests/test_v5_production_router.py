import unittest
from agentforge.features.film_studio import production_router


class ProductionRouterTests(unittest.TestCase):
    def test_only_allowed_route(self):
        brief = {"max_cloud_seconds": 30}
        options = [{"method": "local", "id": "local_ltx"}, {"method": "cloud", "id": "cloud_ltx"}]
        selected = production_router.choose(brief, options, lambda *_: {"choice": "cloud:cloud_ltx", "reason": "Longer shots"})
        self.assertEqual(selected["motion_ref"], "cloud_ltx")
        self.assertEqual(selected["max_cloud_seconds"], 30)
        with self.assertRaises(ValueError):
            production_router.choose(brief, options, lambda *_: {"choice": "cloud:unregistered", "reason": "x"})

    def test_automatic_budget_is_deferred_to_timeline(self):
        plan = production_router.choose({}, [{"method": "cloud", "id": "cloud"}], lambda *_: self.fail("No AI needed"))
        self.assertEqual(plan["cloud_budget_mode"], "timeline")
        self.assertEqual(plan["max_cloud_seconds"], 0)

    def test_one_route_without_ai_call(self):
        def no_inference(*args):
            self.fail("Single route does not need inference")
        self.assertEqual(production_router.choose({"max_cloud_seconds": 0},
            [{"method": "local", "id": "owner"}], no_inference)["method"], "local")
