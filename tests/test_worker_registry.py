import tempfile
import unittest
from pathlib import Path

from agentforge.worker_registry import (
    WorkerConfigError,
    load_worker,
)


class TestWorkerRegistry(unittest.TestCase):

    def create_fixture(
        self,
        root,
        model_ref="local_qwen",
        enabled=True,
        instructions="Test instructions",
        extra="",
        runtime="manual",
    ):
        root = Path(root)

        config = root / "config"
        worker = root / "workers" / "test_worker"

        config.mkdir(parents=True)
        worker.mkdir(parents=True)

        flag = "true" if enabled else "false"

        (config / "models.toml").write_text(
            '[models.local_qwen]\n'
            'provider = "ollama"\n'
            'model = "qwen3:8b"\n'
            'base_url = "http://127.0.0.1:11434"\n'
            f'enabled = {flag}\n',
            encoding="utf-8",
        )

        (worker / "worker.toml").write_text(
            'id = "test_worker"\n'
            f'model_ref = "{model_ref}"\n'
            f'runtime = "{runtime}"\n'
            'capabilities = ["source_review"]\n'
            + extra,
            encoding="utf-8",
        )

        (worker / "instructions.md").write_text(
            instructions,
            encoding="utf-8",
        )

        return root

    def test_opportunity_researcher(self):
        profile = load_worker("opportunity_researcher")
        self.assertEqual(profile["model_ref"], "local_qwen")
        self.assertEqual(profile["model"]["model"], "qwen3:8b")
        self.assertEqual(profile["runtime"], "langgraph")

    def test_source_reviewer(self):
        profile = load_worker("source_reviewer")
        self.assertEqual(profile["runtime"], "manual")

    def test_reject_path_traversal(self):
        with self.assertRaises(WorkerConfigError):
            load_worker("../config")

    def test_reject_unknown_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.create_fixture(
                temp, model_ref="missing_model"
            )
            with self.assertRaises(WorkerConfigError):
                load_worker("test_worker", root=root)

    def test_reject_disabled_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.create_fixture(temp, enabled=False)
            with self.assertRaises(WorkerConfigError):
                load_worker("test_worker", root=root)

    def test_reject_empty_instructions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.create_fixture(temp, instructions="")
            with self.assertRaises(WorkerConfigError):
                load_worker("test_worker", root=root)

    def test_reject_secret_field(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.create_fixture(
                temp,
                extra='api_key = "must-not-be-here"\n',
            )
            with self.assertRaises(WorkerConfigError):
                load_worker("test_worker", root=root)


if __name__ == "__main__":
    unittest.main()
