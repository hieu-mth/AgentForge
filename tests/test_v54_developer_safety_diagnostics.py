"""V5.4: precise, redacted React source guardrails (no model or JS execution)."""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import skill_runner, webapp_developer as dev
from tests.test_webapp_developer_v42b import APP, CSS, MODEL


class DeveloperSafetyDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        for field, value in (
            ("PROPOSALS", folder / "proposals"),
            ("PROJECTS", folder / "projects"),
        ):
            obj = patch.object(dev, field, value)
            obj.start()
            self.addCleanup(obj.stop)

    def test_inline_svg_namespace_is_not_an_external_resource(self):
        app = APP.replace(
            '<h1>Cửa hàng demo</h1>',
            '<h1>Cửa hàng demo</h1>'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlnsXlink="http://www.w3.org/1999/xlink" '
            'viewBox="0 0 24 24" role="img">'
            '<circle cx="12" cy="12" r="8" /></svg>')
        candidate = deepcopy(MODEL)
        candidate["files"][0]["content"] = app
        self.assertIsNone(dev._unsafe_reason(app, "src/App.jsx"))
        with patch("agentforge.model.generate_json", return_value=candidate) as model:
            receipt = dev.propose("svg-demo", "Tạo một cửa hàng nệm demo local.")
            model.assert_called_once()
        proposal, _ = dev._read_proposal(receipt["proposal_id"])
        self.assertEqual(proposal["status"], "PROPOSED_NOT_APPLIED")
        self.assertFalse(proposal["execution_authorized"])
        self.assertFalse(dev.PROJECTS.exists())
        source = {f["path"]: f["content"] for f in proposal["files"]}
        self.assertEqual(source["src/App.jsx"], app)
        self.assertEqual(source["src/styles.css"], CSS)

    def test_svg_namespace_is_scoped_to_attribute_not_remote_source(self):
        cases = (
            ('<img src="https://example.invalid/photo.png" />', "REMOTE_URL"),
            ('<svg><image href="http://www.w3.org/2000/svg" /></svg>', "REMOTE_URL"),
            ('const url = "http://www.w3.org/2000/svg";', "REMOTE_URL"),
            ('<script type="module"></script>', "EMBEDDED_HTML"),
            ('<iframe title="external" />', "EMBEDDED_HTML"),
            ('const cart = fetch("/orders");', "ACTIVE_API"),
            ('const cart = window.location;', "ACTIVE_API"),
            ('const x = import("./helpers.js");', "DYNAMIC_IMPORT"),
            ('const x = new Function("return true");', "ACTIVE_API"),
            ('const x = eval("alert(1)");', "ACTIVE_API"),
        )
        for source, reason in cases:
            with self.subTest(source=source[:45]):
                self.assertEqual(dev._unsafe_reason(source, "src/App.jsx"), reason)
        self.assertEqual(dev._unsafe_reason("background: url(data:image/png;base64,123);",
                                             "src/styles.css"), "CSS_ASSET")
        self.assertEqual(dev._unsafe_reason("@import 'styles.css';",
                                             "src/styles.css"), "CSS_ASSET")

    def test_no_false_positive_for_longer_custom_component_names(self):
        self.assertIsNone(dev._unsafe_reason(
            "function App(){ return <BaseBadge />; }", "src/App.jsx"))
        self.assertIsNone(dev._unsafe_reason(
            "function App(){ return <ScriptLabel />; }", "src/App.jsx"))
        self.assertEqual(dev._unsafe_reason("<base href='/'>", "src/App.jsx"),
                         "EMBEDDED_HTML")

    def test_each_rejected_rule_is_redacted_and_actionable(self):
        source_cases = {
            "REMOTE_URL": 'const link = "https://credentials.example/secret";',
            "ACTIVE_API": "fetch('/local');",
            "DYNAMIC_IMPORT": "import('./helpers.js');",
            "EMBEDDED_HTML": "<iframe />",
            "CSS_ASSET": "body {background: url('secret.png')}",
        }
        for rule, code in source_cases.items():
            with self.subTest(rule=rule):
                candidate = deepcopy(MODEL)
                path = "src/styles.css" if rule == "CSS_ASSET" else "src/App.jsx"
                idx = 1 if path.endswith(".css") else 0
                candidate["files"][idx]["content"] += "\n" + code
                with patch("agentforge.model.generate_json", return_value=candidate) as model:
                    with self.assertRaisesRegex(ValueError, "APP_CODE_UNSAFE") as err:
                        dev.propose("unsafe-app", "Tạo ứng dụng React demo.")
                    model.assert_called_once()
                safe = skill_runner._safe_failure("webapp.develop", err.exception)
                self.assertTrue(safe.startswith("APP_CODE_UNSAFE:"), safe)
                self.assertNotIn("credentials.example", safe)
                self.assertNotIn("secret.png", safe)
                self.assertNotIn("/local", safe)
                self.assertNotIn("APP_CODE_UNSAFE: " + rule, safe)
        self.assertFalse(dev.PROPOSALS.exists())

    def test_blocked_imports_remain_strict(self):
        for import_line, label in (
            ("import axios from 'axios';", "EXTERNAL_PACKAGE"),
            ("import secret from './not-allowed.js';", "UNAPPROVED_MODULE"),
        ):
            candidate = deepcopy(MODEL)
            candidate["files"][0]["content"] = import_line + "\n" + APP
            with self.subTest(label=label):
                with patch("agentforge.model.generate_json", return_value=candidate):
                    with self.assertRaisesRegex(ValueError, "APP_CODE_UNSAFE: " + label) as err:
                        dev.propose("imports-demo", "Tạo app.")
                safe = skill_runner._safe_failure("webapp.develop", err.exception)
                self.assertTrue(safe.startswith("APP_CODE_UNSAFE:"))
                self.assertNotIn("not-allowed.js", safe)
        self.assertFalse(dev.PROPOSALS.exists())

    def test_unknown_untrusted_error_never_echoed_to_history(self):
        secret = "private-token-DO-NOT-RECORD"
        failure = ValueError("APP_CODE_UNSAFE: " + secret)
        safe = skill_runner._safe_failure("webapp.develop", failure)
        self.assertTrue(safe.startswith("APP_CODE_UNSAFE:"))
        self.assertNotIn(secret, safe)


if __name__ == "__main__":
    unittest.main()
