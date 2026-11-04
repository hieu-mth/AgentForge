"""S1.1: strict contract loading, read-only discovery and schema tests."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import skill_registry as skills


class TestSkillRegistry(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(skills.ROOT / "skills", self.root / "skills")

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, skill_id="web.create"):
        return self.root / "skills" / skill_id / "skill.toml"

    def mutate(self, needle, replacement, *, skill_id="web.create"):
        path = self.manifest(skill_id)
        text = path.read_text(encoding="utf-8")
        self.assertIn(needle, text)
        path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")

    def test_builtin_registry_discovery_is_deterministic(self):
        registry = skills.load_registry(root=self.root)
        self.assertEqual(list(registry), sorted(registry))
        self.assertEqual(set(registry), {
            "web.create", "web.quality_check", "web.browser_test",
            "research.opportunity", "research.source_review",
            "media.compose", "media.image_edit", "media.quality_check",
            "media.video_render", "media.tts", "media.copy_draft",
            "analytics.import", "analytics.quality_check", "analytics.content_report",
            "analytics.trend_report", "analytics.experiment_report",
            "analytics.finance_report", "analytics.opportunity_score",
        })
        for contract in registry.values():
            self.assertEqual(contract["schema_version"], 1)
            self.assertTrue(contract["required_permissions"])
            self.assertFalse("handler" in contract)
            self.assertIn(contract["execution_mode"], skills.MODES)

    def test_load_single_skill_and_validate_input_output(self):
        contract = skills.load_skill("web.create", root=self.root)
        self.assertEqual(contract["worker_id"], "product_builder")
        request = {"slug": "nem-tu-van", "brief": "Tạo landing page cho nệm"}
        self.assertEqual(skills.validate_payload(contract, request), request)
        response = {"proposal_id": "a" * 32, "project_slug": "nem-tu-van",
                    "sha256": "b" * 64, "execution_authorized": False,
                    "proposal_path": "local-only"}
        self.assertEqual(skills.validate_payload(contract, response, direction="output"), response)

    def test_invalid_input_missing_extra_and_wrong_type(self):
        contract = skills.load_skill("web.create", root=self.root)
        for payload in ({"slug": "nem-tu-van"}, 
                        {"slug": 4, "brief": "Tạo landing page"},
                        {"slug": "nem-tu-van", "brief": "Tạo", "extra": "no"}):
            with self.subTest(payload=payload), self.assertRaises(skills.SkillConfigError):
                skills.validate_payload(contract, payload)
        with self.assertRaises(skills.SkillConfigError):
            skills.validate_payload(contract, [])
        with self.assertRaises(skills.SkillConfigError):
            skills.validate_payload(contract, {}, direction="invalid")

    def test_boolean_is_not_integer(self):
        contract = skills.load_skill("web.quality_check", root=self.root)
        with self.assertRaises(skills.SkillConfigError):
            skills.validate_payload(contract, {"status": "PASS", "failures": True,
                                                 "warnings": 0, "findings": []},
                                    direction="output")

    def test_reject_invalid_skill_id_before_file_io(self):
        for bad in ("../etc", "web/quality", "A.B", "web", "", ".hidden", "web.create/.."):
            with self.subTest(bad=bad), self.assertRaises(skills.SkillConfigError):
                skills.load_skill(bad, root=self.root)

    def test_reject_unknown_and_missing_fields(self):
        self.mutate('schema_version = 1', 'schema_version = 1\napi_key = "secret"')
        with self.assertRaisesRegex(skills.SkillConfigError, "unauthorized"):
            skills.load_skill("web.create", root=self.root)
        self.assertRaises(skills.SkillConfigError, skills.load_registry, root=self.root)

    def test_reject_bad_contract_version_worker_and_permission(self):
        cases = [
            ('schema_version = 1', 'schema_version = 2'),
            ('version = "0.1.0"', 'version = "latest"'),
            ('worker_id = "product_builder"', 'worker_id = "../steal"'),
            ('"model.invoke"', '"admin.root"'),
        ]
        for left, right in cases:
            with self.subTest(right=right):
                backup = self.manifest().read_text(encoding="utf-8")
                self.mutate(left, right)
                with self.assertRaises(skills.SkillConfigError):
                    skills.load_skill("web.create", root=self.root)
                self.manifest().write_text(backup, encoding="utf-8")

    def test_reject_bad_schema_and_required_fields(self):
        self.mutate('required = ["slug", "brief"]', 'required = ["nonexistent"]')
        with self.assertRaisesRegex(skills.SkillConfigError, "required fields"):
            skills.load_registry(root=self.root)

    def test_reject_read_only_declaring_model_or_write(self):
        self.mutate('required_permissions = ["workspace.read"]',
                    'required_permissions = ["workspace.read", "model.invoke"]',
                    skill_id="web.quality_check")
        with self.assertRaisesRegex(skills.SkillConfigError, "Read-only"):
            skills.load_registry(root=self.root)

    def test_reject_symlink_manifest_and_directory(self):
        source = self.manifest()
        outside = self.root / "outside.toml"
        outside.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        source.unlink()
        try:
            source.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unavailable")
        with self.assertRaises(skills.SkillConfigError):
            skills.load_registry(root=self.root)

    def test_no_handlers_imported_or_called_during_discovery(self):
        with (patch("agentforge.model.generate") as model,
              patch("subprocess.run") as shell,
              patch("urllib.request.urlopen") as network):
            registry = skills.load_registry(root=self.root)
            self.assertEqual(len(registry), 18)
            model.assert_not_called()
            shell.assert_not_called()
            network.assert_not_called()

    def test_cli_list_validate_inspect_are_read_only(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with patch.object(skills, "ROOT", self.root):
            for command in ("list", "validate", "inspect"):
                with self.subTest(command=command):
                    stdout = StringIO()
                    argv = ["skill_registry", command]
                    if command == "inspect":
                        argv.append("web.create")
                    with patch("sys.argv", argv), redirect_stdout(stdout):
                        skills.main()
                    result = json.loads(stdout.getvalue())
                    if command == "validate":
                        self.assertEqual(result["skill_count"], 18)
                    elif command == "list":
                        self.assertEqual(len(result), 18)
                        self.assertTrue(all(not item["invocation_enabled"] for item in result))
                    else:
                        self.assertFalse(result["invocation_enabled"])


if __name__ == "__main__":
    unittest.main()
