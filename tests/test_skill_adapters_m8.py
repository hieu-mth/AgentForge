"""M8: domain skill adapters preserve the approved grants and lazy dispatch."""
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from agentforge import skill_registry, skill_runner
from agentforge.core import skill_adapters
from agentforge.core.skill_adapters import analytics, growth, media, research, web


class DomainSkillAdapterTests(unittest.TestCase):
    def test_all_manifests_have_exactly_one_reviewed_code_policy(self):
        registry = skill_registry.load_registry()
        self.assertEqual(set(registry), set(skill_adapters.POLICY))
        modules = (web, research, media, analytics, growth)
        self.assertEqual(sum(len(module.POLICY) for module in modules), 30)
        for skill_id, contract in registry.items():
            with self.subTest(skill_id=skill_id):
                worker, mode, permissions = skill_adapters.POLICY[skill_id]
                self.assertEqual(worker, contract["worker_id"])
                self.assertEqual(mode, contract["execution_mode"])
                self.assertEqual(permissions, frozenset(contract["required_permissions"]))
                self.assertIs(skill_runner.POLICY, skill_adapters.POLICY)

    def test_unknown_adapter_refused_before_import_or_execution(self):
        with patch("agentforge.product_builder.propose") as model:
            with self.assertRaisesRegex(PermissionError, "No trusted adapter"):
                skill_adapters.dispatch("fake.execute", {"brief": "untrusted"})
            model.assert_not_called()

    def test_web_proposal_revision_kwargs_are_preserved(self):
        payload = {"slug": "site", "brief": "new", "source_proposal_id": "prior",
                   "source_sha256": "a" * 64, "revision_feedback": "change header"}
        with patch("agentforge.product_builder.propose", return_value={"id": "ok"}) as mock:
            self.assertEqual(skill_adapters.dispatch("web.create", payload), {"id": "ok"})
            mock.assert_called_once_with("site", "new", source_proposal_id="prior",
                                         source_sha256="a" * 64,
                                         revision_feedback="change header")

    def test_webapp_development_architecture_kwargs_are_preserved(self):
        payload = {"slug": "store", "brief": "cart", "architecture_id": "arch",
                   "architecture_sha": "a" * 64}
        with patch("agentforge.webapp_developer.propose", return_value={"id": "ok"}) as mock:
            skill_adapters.dispatch("webapp.develop", payload)
            mock.assert_called_once_with("store", "cart", architecture_id="arch",
                                         architecture_sha="a" * 64)

    def test_research_stdout_is_captured(self):
        with patch("agentforge.research.run", side_effect=lambda topic: print("private prompt") or {"topic": topic}):
            out = StringIO()
            with redirect_stdout(out):
                result = skill_adapters.dispatch("research.opportunity", {"topic": "local"})
            self.assertEqual(result, {"topic": "local"})
            self.assertEqual(out.getvalue(), "")

    def test_media_external_run_confirmation_preserved(self):
        with patch("agentforge.media_render.render_video", return_value={"status": "ok"}) as mock:
            skill_adapters.dispatch("media.video_render", {"run_id": "run"})
            mock.assert_called_once_with("run", confirm_external_run=True)

    def test_analytics_and_growth_still_route_to_named_functions(self):
        with patch("agentforge.analytics_insights.finance_report", return_value={"ok": 1}) as finance:
            self.assertEqual(skill_adapters.dispatch("analytics.finance_report",
                             {"dataset": "demo", "campaign": "c"}), {"ok": 1})
            finance.assert_called_once_with("demo", campaign="c")
        with patch("agentforge.growth_reports.report", return_value={"ok": 2}) as report:
            self.assertEqual(skill_adapters.dispatch("growth.report",
                             {"campaign": "c"}), {"ok": 2})
            report.assert_called_once_with("c")


if __name__ == "__main__":
    unittest.main()
