"""Public task serialization is independent of legacy HTML dashboards."""
import unittest

from agentforge.core.public_serialization import _artifact_names, _task_public


class PublicSerializationTests(unittest.TestCase):
    def test_task_metadata_allowlist(self):
        task = {
            "task_id": "a", "kind": "skill", "skill_id": "web.create",
            "parent_id": None, "status": "SUCCEEDED", "created_at": "now",
            "updated_at": "now", "error": None,
            "request": {"secret": "private"}, "result": {"private": "output"},
        }
        public = _task_public(task)
        self.assertEqual(set(public), {
            "task_id", "kind", "skill_id", "parent_id", "status",
            "created_at", "updated_at", "error"})
        self.assertNotIn("private", str(public))

    def test_only_basenames(self):
        result = {"proposal_path": r"D:\\Private\\Customer\\proposal.json",
                  "nested": {"image_path": "/tmp/owner/image.png"}}
        self.assertEqual(_artifact_names(result), ["proposal.json", "image.png"])

    def test_unknown_paths_ignored_and_depth_bounded(self):
        self.assertEqual(_artifact_names({"request": {"secret": "x"}}), [])
        nested = {"a": {"b": {"c": {"d": {"e": {
            "proposal_path": "/tmp/d.pdf"}}}}}}
        self.assertEqual(_artifact_names(nested), [])

    def test_screenshot_limit(self):
        self.assertEqual(len(_artifact_names({
            "screenshots": [f"/tmp/{i}.png" for i in range(20)]})), 6)


if __name__ == "__main__":
    unittest.main()
