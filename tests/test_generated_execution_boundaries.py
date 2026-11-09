"""No host execution/Owner-origin preview; restricted Docker command contracts.

Docker is mocked here: these tests do not establish real isolation on hardware.
"""
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from agentforge import webapp_builder as base, webapp_developer as dev, webapp_sandbox as sandbox
from agentforge.core import artifact_acceptance as acceptance
from tests.test_webapp_developer_v42b import MODEL, BRIEF
import tests.test_webapp_revision_http_v41 as http_fixture


class GeneratedBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db = root / "tasks.db"
        for module, field, value in [(dev, "PROPOSALS", root / "developer"),
                (dev, "PROJECTS", root / "projects"), (base, "PROPOSALS", root / "templates"),
                (sandbox, "QA_STAGING", root / "staging")]:
            context = patch.object(module, field, value)
            context.start()
            self.addCleanup(context.stop)
        model = deepcopy(MODEL)
        model["files"][0]["content"] = (
            "export default function App(){const k='fe'+'tch';"
            "globalThis[k]('/audit-probe');return <main>Demo</main>}")
        with patch("agentforge.model.generate_json", return_value=model), patch("subprocess.run") as process:
            self.proposal = dev.propose("indirect-api", BRIEF)
            process.assert_not_called()
        self.pid, self.sha = self.proposal["proposal_id"], self.proposal["sha256"]
        self.env = patch.dict("os.environ", {"AGENTFORGE_SANDBOX_IMAGE": "sha256:" + "b" * 64,
            "ANTHROPIC_AUTH_TOKEN": "test-only-secret", "OPENAI_API_KEY": "test-only-key",
            "NODE_OPTIONS": "--require untrusted.js", "DOCKER_HOST": "tcp://remote:2375"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def verify(self):
        return sandbox.verify(self.pid, self.sha, confirm_external_run=True)

    def test_indirect_api_syntax_is_not_runtime_safety_or_acceptance(self):
        result = acceptance.validate_source(self.pid, self.sha, db_path=self.db)
        self.assertEqual(result["syntax"]["status"], "PASS")
        self.assertEqual(result["artifact_acceptance"]["status"], "NEEDS_VALIDATION")
        self.assertFalse(result["artifact_acceptance"]["interactive_preview_enabled"])
        doc, _ = dev._read_proposal(self.pid)
        self.assertFalse(doc["execution_authorized"])

    def test_only_local_restricted_docker_gets_source_without_credentials(self):
        def fake(args, **kwargs):
            self.assertEqual(args[0], "trusted-docker")
            self.assertEqual(args[1:3], ["-H", sandbox._local_docker_host()])
            self.assertNotIn("tcp://remote:2375", str(args))
            for name in ("ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "NODE_OPTIONS", "DOCKER_HOST"):
                self.assertNotIn(name, kwargs["env"])
            if "image" in args:
                return SimpleNamespace(returncode=0, stdout="linux\n")
            for flag in ("--read-only", "--cap-drop", "--security-opt", "--pids-limit", "--cpus", "--memory"):
                self.assertIn(flag, args)
            self.assertEqual(args[args.index("--network") + 1], "none")
            self.assertEqual(args[args.index("--user") + 1], "10001:10001")
            self.assertEqual(args[args.index("--pull") + 1], "never")
            self.assertNotIn("--publish", args)
            self.assertNotIn("/audit-probe", args[-1])  # No source interpolation into shell text.
            self.assertIn('7.3.7', args[-1])
            self.assertIn('0.28.1', args[-1])
            self.assertIn("readonly", args[args.index("--mount") + 1])
            self.assertEqual(kwargs["timeout"], 150)
            return SimpleNamespace(returncode=0)
