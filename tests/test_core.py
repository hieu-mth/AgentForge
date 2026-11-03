import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agentforge import workflow


class TestAgentForgeCore(unittest.TestCase):

    def test_run_and_restore_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite"

            with patch.object(workflow, "DB", db):
                with patch.object(
                    workflow,
                    "generate",
                    return_value="Verified test response"
                ) as model:
                    output = io.StringIO()

                    with redirect_stdout(output):
                        workflow.run_task("Test business task")

                    text = output.getvalue()

                    self.assertIn("STATUS: completed", text)
                    model.assert_called_once_with("Test business task")

                task_id = next(
                    line.split("TASK ID: ", 1)[1]
                    for line in text.splitlines()
                    if line.startswith("TASK ID: ")
                )

                restored = io.StringIO()

                with redirect_stdout(restored):
                    workflow.show_status(task_id)

                self.assertIn("STATUS: completed", restored.getvalue())
                self.assertIn("NEXT: ()", restored.getvalue())
                self.assertIn(
                    "Verified test response",
                    restored.getvalue()
                )

    def test_empty_model_response_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite"

            with patch.object(workflow, "DB", db):
                with patch.object(workflow, "generate", return_value=""):
                    with redirect_stdout(io.StringIO()):
                        with self.assertRaises(RuntimeError):
                            workflow.run_task("Test empty response")


if __name__ == "__main__":
    unittest.main()
