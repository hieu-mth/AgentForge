"""Real parser tests: source is parsed as data, never imported or executed."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from agentforge import webapp_developer as dev, skill_runner
from agentforge.core import artifact_acceptance as acceptance
from agentforge.domains.webapps import syntax, architect, static_qa, reviewer
from tests.test_webapp_developer_v42b import MODEL, BRIEF
import tests.test_v5_company as v5

INVALID = "export default function App(){ return <div>broken; }"


class SourceSyntaxTests(unittest.TestCase):
    def test_audit_invalid_jsx_and_broken_javascript_are_detected(self):
        for code in (INVALID, "export default function App( { return <main/>; }", "const x = ;"):
            report = syntax.check_files([{"path": "src/App.jsx", "content": code}], "b" * 64)
            self.assertEqual(report["status"], "FAIL", code)
            self.assertEqual(report["source_sha"], "b" * 64)
            self.assertTrue(report["diagnostics"])
            self.assertFalse(report["generated_code_executed"])
            self.assertFalse(report["build_verified"])

    def test_generation_rejects_bad_source_with_redacted_diagnostics_and_no_retry(self):
        model = deepcopy(MODEL)
        model["files"][0]["content"] = INVALID
        with tempfile.TemporaryDirectory() as folder, patch.object(dev, "PROPOSALS", Path(folder) / "proposals"), \
             patch("agentforge.model.generate_json", return_value=model) as inference, \
             patch("subprocess.run") as process:
            with self.assertRaises(syntax.SourceSyntaxError) as raised:
                dev.propose("bad-source", BRIEF)
            inference.assert_called_once()
            process.assert_not_called()
            self.assertFalse(dev.PROPOSALS.exists())
            error = skill_runner._safe_failure("webapp.develop", raised.exception)
            self.assertIn("src/App.jsx:1:", error)
            self.assertNotIn("<div>broken", error)

    def test_valid_jsx_report_is_bound_to_exact_proposal_sha(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dev, "PROPOSALS", Path(folder)), \
             patch("agentforge.model.generate_json", return_value=MODEL), patch("subprocess.run") as process:
            proposal = dev.propose("good-source", BRIEF)
            doc, _ = dev._read_proposal(proposal["proposal_id"])
            report = syntax.read_report(dev.PROPOSALS, doc["proposal_id"], doc["sha256"], doc["files"])
            self.assertEqual(report["syntax"]["stage"], "SYNTAX_VALID")
            self.assertFalse(report["syntax"]["build_verified"])
            with self.assertRaisesRegex(PermissionError, "SOURCE_STALE"):
                syntax.read_report(dev.PROPOSALS, doc["proposal_id"], "0" * 64, doc["files"])
            process.assert_not_called()

    def test_old_malformed_proposal_remains_readable_but_static_qa_fails(self):
        fixture = v5.V5CompanyTests("test_fixed_four_role_plan_three_calls_and_zero_external_processes")
        fixture.setUp()
        try:
            with patch("agentforge.model.generate_json", side_effect=[v5.ARCH, MODEL]):
                arch = architect.propose("historical-app", v5.BRIEF)
                proposal = dev.propose("historical-app", v5.BRIEF, **arch_fields(arch))
            doc, path = dev._read_proposal(proposal["proposal_id"])
            malformed = deepcopy(MODEL)
            malformed["files"][0]["content"] = INVALID
            doc["files"] = dev._compile(dev.validate_code(malformed, check_syntax=False), "historical-app")
            doc["sha256"] = dev._digest(doc["project_slug"], doc["brief"], doc["title"], doc["summary"],
                                       doc["files"], architecture=doc["architecture"])
            path.write_text(json.dumps(doc), encoding="utf-8")
            before = path.read_bytes()
            dev._read_proposal(doc["proposal_id"])
            qa = static_qa.audit(doc["proposal_id"], doc["sha256"])
            self.assertEqual(qa["status"], "FAIL_SYNTAX")
