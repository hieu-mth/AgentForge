"""Owner-only bridge from reviewed AI storyboard to local MP4.

Does not invoke a real model or FFmpeg; verifies exact SHA and explicit gates.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agentforge import quality_v14
from agentforge.api.routes import media as media_routes, read as read_routes

ID = "a" * 32
SHA = "b" * 64
STORY = {
    "title": "Tư vấn chọn nệm",
    "scenes": [
        {"headline": "Chọn nệm", "caption": "Trao đổi nhu cầu nệm",
         "duration_seconds": 5},
        {"headline": "Liên hệ", "caption": "Hỏi để chọn nệm phù hợp",
         "duration_seconds": 5},
    ],
    "status": "DRAFT_NOT_VERIFIED",
    "review_required": True,
    "verified_claims": False,
}


class MediaDashboardFlowTests(unittest.TestCase):
    def setUp(self):
        self.sha = quality_v14._sha(STORY)
        self.task = {
            "task_id": ID, "status": "SUCCEEDED",
            "skill_id": "media.copy_draft", "result": STORY, "events": [],
        }
        self.server = SimpleNamespace(task_db_path=None, allow_external_actions=True)
        self.session = {"inspected_storyboard_tasks": {ID: self.sha}}

    def test_prepared_assets_require_inspection_sha_and_fixed_task(self):
        payload = {"ack": "PREPARE_REVIEWED_STORYBOARD",
                   "task_id": ID, "source_sha": self.sha}
        with patch("agentforge.task_history.get_task", return_value=self.task), \
             patch("agentforge.features.media.workflow.prepare",
                   return_value={"status": "ASSETS_READY"}) as prepare:
            out = media_routes.handle(self.server, "/api/media/prepare-from-task",
                                      payload, session=self.session)
            self.assertEqual(out["status"], "ASSETS_READY")
            args, kwargs = prepare.call_args
            self.assertTrue(args[0]["slug"].startswith("video-"))
            self.assertEqual(args[0]["title"], STORY["title"])
            self.assertEqual(args[0]["scenes"], STORY["scenes"])
            self.assertTrue(kwargs["confirm_edit"])
            for sess, sha in (({}, self.sha), (self.session, "c" * 64)):
                with self.assertRaises(PermissionError):
                    media_routes.handle(self.server, "/api/media/prepare-from-task",
                                        {**payload, "source_sha": sha}, session=sess)
            self.assertEqual(prepare.call_count, 1)

    def test_unreviewed_modified_and_failed_model_results_refused(self):
        payload = {"ack": "PREPARE_REVIEWED_STORYBOARD",
                   "task_id": ID, "source_sha": self.sha}
        for changed in (
            {**self.task, "status": "FAILED"},
            {**self.task, "result": {**STORY, "title": "Edited"}},
            {**self.task, "result": {**STORY, "verified_claims": True}},
            {**self.task, "skill_id": "media.compose"},
        ):
            with self.subTest(changed=changed), \
                 patch("agentforge.task_history.get_task", return_value=changed), \
                 patch("agentforge.features.media.workflow.prepare") as prepare:
                with self.assertRaises((PermissionError, ValueError)):
                    media_routes.handle(self.server, "/api/media/prepare-from-task",
                                        payload, session=self.session)
                prepare.assert_not_called()

    def test_render_requires_local_mode_explicit_ack_and_exact_source_sha(self):
        production = {"storyboard_sha": SHA, "status": "ASSETS_READY"}
        payload = {"ack": "RENDER_LOCAL_MP4", "storyboard_sha": SHA}
        route = "/api/videos/" + ID + "/render"
        with patch("agentforge.media_workflow_v15._row", return_value=production), \
             patch("agentforge.media_workflow_v15.render",
                   return_value={"status": "VIDEO_READY"}) as render:
            for bad in ({**payload, "storyboard_sha": "c" * 64},
                        {**payload, "ack": "RUN"}, {**payload, "extra": True}):
                with self.assertRaises(PermissionError):
                    media_routes.handle(self.server, route, bad, session={})
            self.server.allow_external_actions = False
            with self.assertRaises(PermissionError):
                media_routes.handle(self.server, route, payload, session={})
            self.server.allow_external_actions = True
            result = media_routes.handle(self.server, route, payload, session={})
            self.assertEqual(result["status"], "VIDEO_READY")
            render.assert_called_once_with(ID, confirm_local_process=True)

    def test_inspect_task_binds_sha_in_session(self):
        class Handler:
            server = SimpleNamespace(task_db_path=None)
            def __init__(self):
                self.session = {}
            def _session(self):
                return self.session
            def _reply(self, status, body):
                return body
        handler = Handler()
        with patch("agentforge.task_history.get_task", return_value=self.task), \
             patch("agentforge.api.routes.read._public_task",
                   return_value={"task_id": ID, "report": {"kind": "storyboard"}}):
            response = read_routes.dispatch(handler, "/api/tasks/" + ID)
        self.assertEqual(response["storyboard_source_sha"], self.sha)
        self.assertEqual(handler.session["inspected_storyboard_tasks"][ID], self.sha)


if __name__ == "__main__":
    unittest.main()
