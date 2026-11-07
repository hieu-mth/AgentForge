"""V4.2 sandbox safety contract: only pinned, approved, offline Docker QA."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentforge import (
    brain_planner, brain_store, skill_runner, webapp_builder, webapp_sandbox,
)
from tests.test_webapp_builder_v40 import SPEC, BRIEF


IMAGE = "sha256:" + "b" * 64


class WebappSandboxV42Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for mod, attr, value in (
            (webapp_builder, "PROJECTS", root / "projects"),
            (webapp_builder, "PROPOSALS", root / "proposals"),
            (webapp_sandbox, "QA_STAGING", root / "staging"),
        ):
            p = patch.object(mod, attr, value)
            p.start()
            self.addCleanup(p.stop)
        with patch("agentforge.model.generate_json", return_value=SPEC) as model:
            self.proposal = webapp_builder.propose("demo-app", BRIEF)
            model.assert_called_once()
        self.env = patch.dict("os.environ", {
            "AGENTFORGE_SANDBOX_IMAGE": IMAGE,
            "ANTHROPIC_API_KEY": "sensitive-test-key",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def _verify(self, sha=None, approved=True):
        return webapp_sandbox.verify(
            self.proposal["proposal_id"],
            sha if sha is not None else self.proposal["sha256"],
            confirm_external_run=approved)

    def test_missing_approval_never_contacts_process_or_model(self):
        with patch("subprocess.run") as proc:
            with self.assertRaisesRegex(PermissionError, "SANDBOX_APPROVAL_REQUIRED"):
                self._verify(approved=False)
            proc.assert_not_called()
        self.assertFalse(webapp_sandbox.QA_STAGING.exists())

    def test_sha_mismatch_rejected_before_docker(self):
        with patch("subprocess.run") as proc:
            with self.assertRaisesRegex(PermissionError, "SANDBOX_SOURCE_STALE"):
                self._verify(sha="0" * 64)
            proc.assert_not_called()
        self.assertFalse(webapp_sandbox.QA_STAGING.exists())

    def test_missing_pinned_image_and_missing_docker_fail_closed(self):
        with patch.dict("os.environ", {"AGENTFORGE_SANDBOX_IMAGE": ""}):
            with patch("subprocess.run") as proc:
                with self.assertRaisesRegex(RuntimeError, "SANDBOX_UNAVAILABLE"):
                    self._verify()
                proc.assert_not_called()
        with (patch("shutil.which", return_value=None),
              patch("subprocess.run") as proc):
            with self.assertRaisesRegex(RuntimeError, "SANDBOX_UNAVAILABLE"):
                self._verify()
            proc.assert_not_called()
        self.assertFalse(webapp_sandbox.QA_STAGING.exists())

    def test_pinned_but_windows_container_image_denied(self):
        with (patch("shutil.which", return_value="docker"),
              patch("subprocess.run", return_value=SimpleNamespace(
                  returncode=0, stdout="windows\n")) as runner):
            with self.assertRaisesRegex(RuntimeError, "SANDBOX_UNAVAILABLE"):
                self._verify()
            runner.assert_called_once()
        self.assertFalse(webapp_sandbox.QA_STAGING.exists())

    def test_success_uses_exact_safe_docker_flags_and_signed_files(self):
        commands = []
        def fake_process(args, **kwargs):
            commands.append((args, kwargs))
            if "image" in args:
                self.assertIn("inspect", args)
                return SimpleNamespace(returncode=0, stdout="linux\n")
            self.assertIn("run", args)
            self.assertNotIn("npm", args[:args.index("--entrypoint")])
            self.assertIn("--network", args)
            self.assertEqual(args[args.index("--network")+1], "none")
            self.assertIn("--read-only", args)
            self.assertIn("--cap-drop", args)
            self.assertIn("ALL", args)
            self.assertIn("--pull", args)
            self.assertEqual(args[args.index("--pull")+1], "never")
            self.assertIn("--memory", args)
            self.assertIn("--pids-limit", args)
            self.assertIn("--tmpfs", args)
            self.assertIn("--user", args)
            self.assertEqual(args[args.index("--user")+1], "10001:10001")
            mount = args[args.index("--mount")+1]
            self.assertIn(",readonly", mount)
            source = Path(mount.split("source=",1)[1].split(",target=",1)[0])
            self.assertTrue((source / "src" / "App.jsx").is_file())
            self.assertTrue((source / "app.json").is_file())
            self.assertFalse((source / ".env").exists())
            self.assertNotIn("ANTHROPIC_API_KEY", str(kwargs["env"]))
            self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
            self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
            self.assertIn("npm run test && npm run build", args[-1])
            return SimpleNamespace(returncode=0)
        with (patch("shutil.which", return_value="docker"),
              patch("subprocess.run", side_effect=fake_process) as runner):
            result = self._verify()
            self.assertEqual(runner.call_count, 2)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["model_called"])
        self.assertEqual(result["network"], "none")
        self.assertEqual(result["source_mount"], "read_only")
        self.assertEqual(list(webapp_sandbox.QA_STAGING.iterdir()), [])

    def test_timeout_triggers_container_removal_and_cleans_stage(self):
        commands = []
        def fake(args, **kwargs):
            commands.append(args)
            if "image" in args:
                return SimpleNamespace(returncode=0, stdout="linux\n")
            if "run" in args:
                raise subprocess.TimeoutExpired(args, 150)
            self.assertEqual(args[args.index("container")+1:args.index("container")+3],
                             ["rm", "-f"])
            return SimpleNamespace(returncode=0)
        with (patch("shutil.which", return_value="docker"),
              patch("subprocess.run", side_effect=fake)):
            with self.assertRaisesRegex(RuntimeError, "SANDBOX_TIMEOUT"):
                self._verify()
        self.assertEqual(len(commands), 3)
        self.assertEqual(list(webapp_sandbox.QA_STAGING.iterdir()), [])

    def test_failed_build_does_not_create_pass_result(self):
        def fake(args, **kwargs):
            if "image" in args:
                return SimpleNamespace(returncode=0, stdout="linux\n")
            return SimpleNamespace(returncode=4)
        with (patch("shutil.which", return_value="docker"),
              patch("subprocess.run", side_effect=fake)):
            with self.assertRaisesRegex(RuntimeError, "SANDBOX_BUILD_FAILED"):
                self._verify()
        self.assertEqual(list(webapp_sandbox.QA_STAGING.iterdir()), [])

    def test_goal_requires_separate_external_run_budget_and_input_consent(self):
        payload = {"proposal_id": self.proposal["proposal_id"],
                   "sha256": self.proposal["sha256"],
                   "confirm_external_run": True}
        with self.assertRaisesRegex(brain_store.BrainError, "cap"):
            brain_planner.make_plan("webapp.qa", payload, max_external_runs=0)
        plan = brain_planner.make_plan("webapp.qa", payload, max_external_runs=1)
        self.assertEqual(plan[0]["skill_id"], "webapp.sandbox_test")
        self.assertEqual(plan[0]["estimated_model_calls"], 0)
        self.assertTrue(plan[0]["external_process"])
        self.assertEqual(skill_runner.missing_grants(
            "webapp.sandbox_test", payload=payload),
            ["confirm_external_run", "process.run"])
        self.assertEqual(skill_runner.missing_grants(
            "webapp.sandbox_test", grants=("process.run",),
            confirm_external_run=True, payload=payload), [])
        self.assertEqual(skill_runner._safe_failure(
            "webapp.sandbox_test", RuntimeError("SANDBOX_UNAVAILABLE: abc")),
            "SANDBOX_UNAVAILABLE: Configure Docker and a pinned local Linux QA image.")
        with self.assertRaises(brain_store.BrainError):
            brain_planner.make_plan(
                "webapp.qa", {**payload, "confirm_external_run": False},
                max_external_runs=1)


if __name__ == "__main__":
    unittest.main()
