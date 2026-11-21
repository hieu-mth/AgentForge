import os
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_pipeline
from agentforge.features.film_studio import draft_resources
from agentforge.features.media import visual_jobs
from agentforge.integrations import comfy_service as service


class GPUAdmissionTests(unittest.TestCase):
    def test_os_releases_orphaned_lock_file_and_blocks_other_process(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "gpu.worker"
        child = "from agentforge.ai.model_hub import local_process_slot\n"
        child += "import os,sys\nfrom pathlib import Path\n"
        child += "try:\n with local_process_slot(Path(sys.argv[1]), 'busy'): os._exit(0)\n"
        child += "except PermissionError: sys.exit(9)\n"
        with model_hub.local_process_slot(path, "busy"):
            self.assertEqual(subprocess.run([sys.executable, "-c", child, str(path)], timeout=10).returncode, 9)
        self.assertEqual(subprocess.run([sys.executable, "-c", child, str(path)], timeout=10).returncode, 0)
        self.assertTrue(path.exists())
        with model_hub.local_process_slot(path, "busy"):
            pass

    def test_missing_measurements_and_threshold_override(self):
        env = {"AGENTFORGE_IMAGE_MIN_COMMIT_MIB": "10000"}
        sample = {"ram_available": 8 << 30, "commit_used": 15 << 30,
                  "commit_limit": 24 << 30, "vram_free_mib": 9000}
        with patch.object(draft_resources, "os", SimpleNamespace(name="nt", environ=env)):
            with self.assertRaisesRegex(draft_resources.ResourceBlocked, "COMMIT_LOW"):
                draft_resources.require_gpu("image", sample)
            with self.assertRaisesRegex(draft_resources.ResourceBlocked, "VRAM_UNAVAILABLE"):
                draft_resources.require_gpu("image", {**sample, "commit_used": 0, "vram_free_mib": None})
            draft_resources.require_gpu("image", {**sample, "commit_used": 0})

    def test_queue_busy_invalid_and_idle(self):
        for state, reason in (({"queue_running": [1], "queue_pending": []}, "COMFYUI_QUEUE_BUSY"),
                              ({"queue_running": []}, "COMFYUI_QUEUE_UNAVAILABLE")):
            with self.subTest(state=state), self.assertRaisesRegex(draft_resources.ResourceBlocked, reason):
                service.validate_idle_queue(state)
        service.validate_idle_queue({"queue_running": [], "queue_pending": []})

    def test_alternate_endpoints_share_admission(self):
        with (patch.object(service, "_settings", return_value={"port": 8192}),
              patch.object(service, "require_idle_queue", side_effect=draft_resources.ResourceBlocked(
                  "COMFYUI_QUEUE_BUSY")) as queue):
            with self.assertRaisesRegex(draft_resources.ResourceBlocked, "COMFYUI_QUEUE_BUSY"):
                service.require_other_queue_idle(8192)
            queue.assert_called_once_with(8188, allow_offline=True)


class ComfyServiceTests(unittest.TestCase):
    def _patch(self, target, name, value, *, create=False):
        self.enterContext(patch.object(target, name, value, create=create))

    def setUp(self):
        tmp_path = self.tmp_path = Path(self.enterContext(TemporaryDirectory()))
        children = []
        for name, value in (("_CHILD", None), ("_PORT", None), ("_STATE", "STOPPED"), ("_ERROR", None),
                            ("LOG_DIR", tmp_path / "logs"), ("RUNTIME_DIR", tmp_path / "runtime")):
            self._patch(service, name, value)
        self._patch(service, "_settings", lambda: {
            "port": 8192, "profile_id": "flux", "install_root": str(tmp_path), "fingerprints": ["fixed"],
        })
        self._patch(service, "_target", lambda ident: (8192, "http://127.0.0.1:8192"))
        self._patch(service, "_launcher", lambda folder: (tmp_path, tmp_path / "python.exe",
                                                                tmp_path / "main.py", ["fixed"]))
        self._patch(service, "os", SimpleNamespace(name="nt"))
        self._patch(ops_control, "require_active", lambda: None)
        self._patch(service.draft_resources, "snapshot", lambda: {})
        self._patch(service.draft_resources, "pressure", lambda sample, stage: None)
        self._patch(service, "_occupied", lambda port: service._owned())
        self._patch(service, "_probe", lambda port: {"devices": []} if service._owned() else None)
        self._patch(service.comfyui, "request_image_bytes",
                            lambda *args, **kwargs: b'{"queue_running":[],"queue_pending":[]}')
        self._patch(service, "_watch_idle", service.reset_idle)
        self._patch(service, "_IDLE_WAKE", threading.Event())
        self._patch(service, "_IDLE_SINCE", None)
        self._patch(model_hub, "last_local_inference", 0.0)
        self._patch(draft_pipeline, "DB", tmp_path / "drafts.sqlite3")
        self._patch(visual_jobs, "DB", tmp_path / "visuals.sqlite3")
        self._patch(subprocess, "CREATE_NO_WINDOW", 0, create=True)

        class Child:
            def __init__(self, command, **options):
                assert "--cache-none" in command and "--disable-auto-launch" in command
                assert options["shell"] is False
                assert command[command.index("--listen") + 1] == "127.0.0.1"
                children.append(self)
                self.pid = len(children)
                self.code = None

            def poll(self):
                return self.code

            def terminate(self):
                self.code = 0

            def wait(self, *, timeout):
                assert self.code == 0

        self._patch(subprocess, "Popen", Child)
        self.children = children


    def test_lifecycle(self):
        assert service.status()["state"] == "STOPPED"
        started = service.control("start")
        assert (started["state"], started["managed"], started["pid"]) == ("RUNNING", True, 1)
        assert service.control("restart")["pid"] == 2
        assert self.children[0].code == 0
        assert service.control("stop")["state"] == "STOPPED"
        assert self.children[1].code == 0


    def test_external_comfy_is_never_adopted_or_stopped(self):
        self._patch(service, "_probe", lambda port: {"devices": []})
        self._patch(service, "_occupied", lambda port: True)
        assert service.ensure_running(8192)
        status = service.status()
        assert status["state"] == "RUNNING"
        assert status["pid"] is None and not status["managed"]
        for action in ("stop", "restart"):
            with self.assertRaisesRegex(PermissionError, "did not launch"):
                service.control(action)
        service._idle_check()
        assert not self.children


    def _idle_clock(self):
        clock = SimpleNamespace(now=0.0)
        service.control("start")
        self._patch(service, "time", SimpleNamespace(monotonic=lambda: clock.now))
        service._idle_check()
        return clock


    def test_idle_lifecycle(self):
        idle_clock = self._idle_clock()
        idle_clock.now = 59.99
        service._idle_check()
        assert self.children[0].code is None
        idle_clock.now = 60
        service._idle_check()
        assert service.status()["state"] == "STOPPED"
        assert self.children[0].code == 0
        assert service.ensure_running(8192)
        assert len(self.children) == 2


    def test_sequential_jobs_reset_countdown_even_between_polls(self):
        idle_clock = self._idle_clock()
        for finished in (59, 110, 160):
            self._patch(model_hub, "last_local_inference", finished)
            idle_clock.now = finished + 2
            service._idle_check()
            assert service._IDLE_SINCE == finished
            assert self.children[0].code is None
        idle_clock.now = 220
        service._idle_check()
        assert self.children[0].code == 0


    def test_admitted_job_while_counting_down(self):
        idle_clock = self._idle_clock()
        idle_clock.now = 60
        with model_hub.local_inference_slot(observe=False):
            service._idle_check()
            assert service._IDLE_SINCE is None
            assert self.children[0].code is None
        service._idle_check()
        idle_clock.now = 120
        service._idle_check()
        assert self.children[0].code == 0


    def test_queued_studio_blocks_idle(self):
        self._assert_busy_work_blocks_idle("studio")

    def test_checkpoint_blocks_idle(self):
        self._assert_busy_work_blocks_idle("checkpoint")

    def test_pending_image_blocks_idle(self):
        self._assert_busy_work_blocks_idle("image")

    def test_provider_job_blocks_idle(self):
        self._assert_busy_work_blocks_idle("provider")

    def test_queue_error_blocks_idle(self):
        self._assert_busy_work_blocks_idle("queue_error")

    def _assert_busy_work_blocks_idle(self, source):
        idle_clock = self._idle_clock()
        idle_clock.now = 60
        if source == "studio":
            draft_pipeline._save({"id": "d" * 32, "status": "QUEUED"})
        elif source == "checkpoint":
            self._patch(draft_pipeline, "ACTIVE", "saving")
        elif source == "image":
            with closing(visual_jobs._db(create=True)) as db, db:
                db.execute("INSERT INTO visual_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           ("a" * 32, "b" * 32, "image", 0, "p", "c", None, "SUBMITTED", None, "sha", "now", "now"))
        elif source == "provider":
            self._patch(service, "_queue_busy", lambda port: True)
        else:
            def no_queue(*args, **kwargs):
                raise TimeoutError()
            self._patch(service.comfyui, "request_image_bytes", no_queue)
        service._idle_check()
        assert self.children[0].code is None
        assert service._IDLE_SINCE is None


    def test_backend_restart_leaves_existing_process_external(self):
        idle_clock = self._idle_clock()
        self._patch(service, "_CHILD", None)
        self._patch(service, "_PORT", None)
        self._patch(service, "_probe", lambda port: {"devices": []})
        idle_clock.now = 120
        service._idle_check()
        assert not service.status()["managed"]
        assert self.children[0].code is None


    def test_new_job_admission_waits_for_final_stop(self):
        idle_clock = self._idle_clock()
        stopping = threading.Event()
        admitted = threading.Event()
        real_stop = service._stop_owned

        def stop():
            stopping.set()
            assert not admitted.wait(0.1)
            real_stop()

        def admit():
            assert stopping.wait(3)
            with model_hub.local_inference_slot():
                assert service.ensure_running(8192)
                admitted.set()

        self._patch(service, "_stop_owned", stop)
        idle_clock.now = 60
        with ThreadPoolExecutor(2) as pool:
            job = pool.submit(admit)
            idle = pool.submit(service._idle_check)
            idle.result(timeout=3)
            job.result(timeout=3)
        assert admitted.is_set()
        assert self.children[0].code == 0 and self.children[1].code is None


    def test_refuse_stop_during_production_or_provider_work(self):
        service.control("start")
        self._patch(draft_pipeline, "ACTIVE", "production")
        with self.assertRaisesRegex(PermissionError, "production"):
            service.control("stop")
        self._patch(draft_pipeline, "ACTIVE", None)
        self._patch(service, "_queue_busy", lambda port: True)
        assert service.status()["busy"]
        with self.assertRaisesRegex(PermissionError, "queue"):
            service.control("restart")
        assert len(self.children) == 1 and self.children[0].code is None


    def test_start_admission_respects_memory(self):
        self._patch(service.draft_resources, "pressure", lambda sample, stage: "COMMIT_LOW")
        with self.assertRaisesRegex(service.StartupPressure, "COMMIT_LOW"):
            service.ensure_running(8192)
        assert not self.children


    def test_other_comfy_process_blocks_duplicate_even_on_a_different_port(self):
        self._patch(service.draft_resources, "snapshot", lambda: {
            "processes": {"comfyui": [{"pid": 987}]},
        })
        with self.assertRaisesRegex(ValueError, "Another ComfyUI process"):
            service.ensure_running(8192)
        assert not self.children


    def test_startup_timeout_and_crash_recovery(self):
        with (patch.object(service, "_probe", lambda port: None),
              patch.object(service, "START_TIMEOUT", 0)):
            with self.assertRaisesRegex(ValueError, "timed out"):
                service.ensure_running(8192)
            with self.assertRaisesRegex(ValueError, "startup was skipped"):
                service.ensure_running(8192)
            assert service.status()["state"] == "ERROR"
            assert len(self.children) == 1
            self.children[0].code = 1
        assert service.control("start")["pid"] == 2

    def test_missing_launcher_and_wrong_endpoint_are_distinct(self):
        with patch.object(service, "_settings", return_value=None):
            with self.assertRaisesRegex(service.StartupError, "COMFYUI_LAUNCHER_REQUIRED"):
                service.ensure_running(8192)
        with self.assertRaisesRegex(service.StartupError, "COMFYUI_ENDPOINT_MISMATCH"):
            service.ensure_running(8188)
        with patch.object(service, "_target", return_value=(8188, "http://127.0.0.1:8188")):
            with self.assertRaisesRegex(service.StartupError, "COMFYUI_ENDPOINT_MISMATCH"):
                service.ensure_running(8192)
        assert not self.children

    def test_spawn_error_is_reported_without_a_managed_process(self):
        with patch.object(subprocess, "Popen", side_effect=OSError(5, "Access denied")):
            with self.assertRaisesRegex(ValueError, "Access denied.*runtime_logs"):
                service.control("start")
        result = service.status()
        self.assertEqual(result["state"], "ERROR")
        self.assertIsNone(result["pid"])

    def test_child_exit_before_readiness_reports_the_exit_code(self):
        spawn = subprocess.Popen

        def exit_immediately(*args, **kwargs):
            child = spawn(*args, **kwargs)
            child.code = 7
            return child

        with patch.object(subprocess, "Popen", side_effect=exit_immediately):
            with self.assertRaisesRegex(ValueError, "PID 1.*exit code 7"):
                service.control("start")
        self.assertEqual(service.status()["state"], "ERROR")
        self.assertEqual(service.control("start")["pid"], 2)

    def test_unbound_timeout_releases_owned_child_for_retry(self):
        with (patch.object(service, "_probe", return_value=None),
              patch.object(service, "_occupied", return_value=False),
              patch.object(service, "START_TIMEOUT", 0)):
            with self.assertRaisesRegex(ValueError, "waiting for /system_stats"):
                service.control("start")
        self.assertEqual(self.children[0].code, 0)
        self.assertEqual(service.status()["state"], "ERROR")
        self.assertEqual(service.control("start")["pid"], 2)

    def test_stop_status_remains_stopping_until_wait_completes(self):
        service.control("start")
        child = self.children[0]
        with patch.object(child, "wait", side_effect=lambda **kw: self.assertEqual(
                service.status()["state"], "STOPPING")):
            self.assertEqual(service.control("stop")["state"], "STOPPED")

    def test_start_waits_for_slow_portable_readiness(self):
        with (patch.object(service, "_probe", side_effect=[None, None, None, {"devices": []}]),
              patch.object(service.time, "sleep") as wait):
            self.assertTrue(service.ensure_running(8192))
        self.assertEqual(wait.call_count, 2)
        self.assertEqual(len(self.children), 1)


    def test_concurrent_automatic_requests_share_process(self):
        entered = threading.Event()
        release = threading.Event()

        def probe(port):
            if service._owned():
                entered.set()
                assert release.wait(5)
                return {"devices": []}
            return None

        self._patch(service, "_probe", probe)
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(service.ensure_running, 8192)
            assert entered.wait(5)
            assert service.status()["state"] == "STARTING"
            second = pool.submit(service.ensure_running, 8192)
            release.set()
            assert first.result(timeout=5)
            assert second.result(timeout=5)
        assert len(self.children) == 1


@unittest.skipUnless(os.name == "nt", "Portable launcher registration is Windows-only")
class ComfyRegistrationTests(unittest.TestCase):
    def test_registration_pins_fixed_files_in_sqlite(self):
        tmp_path = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(model_hub, "DB_PATH", tmp_path / "hub.sqlite3"))
        self.enterContext(patch.object(service, "_target", return_value=(8192, "http://127.0.0.1:8192")))
        self.enterContext(patch.object(service, "_probe", return_value=None))
        self.enterContext(patch.object(service, "_occupied", return_value=False))
        self.enterContext(patch.object(service, "_CHILD", None))
        with self.assertRaisesRegex(ValueError, "could not be read"):
            service.configure("flux", str(tmp_path))
        exe = tmp_path / "python_embeded" / "python.exe"
        script = tmp_path / "ComfyUI" / "main.py"
        for path, body in [(exe, b"MZ binary"), (script, b"import comfy.cli_args")]:
            path.parent.mkdir()
            path.write_bytes(body)
        assert service.configure("flux", str(tmp_path))["profile_id"] == "flux"
        assert service._settings()["install_root"] == str(tmp_path)
        script.write_bytes(b"import comfy.cli_args # changed")
        self.enterContext(patch.object(ops_control, "require_active"))
        self.enterContext(patch.object(service.draft_resources, "pressure", return_value=None))
        self.enterContext(patch.object(service.draft_resources, "snapshot", return_value={}))
        with self.assertRaisesRegex(ValueError, "files changed"):
            service.ensure_running(8192)
