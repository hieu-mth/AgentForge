import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from agentforge import ops_control
from agentforge.ai import model_hub
from agentforge.features.film_studio import draft_pipeline
from agentforge.integrations import comfy_service as service


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    children = []
    for name, value in (("_CHILD", None), ("_PORT", None), ("_STATE", "STOPPED"), ("_ERROR", None),
                        ("LOG_DIR", tmp_path / "logs"), ("RUNTIME_DIR", tmp_path / "runtime")):
        monkeypatch.setattr(service, name, value)
    monkeypatch.setattr(service, "_settings", lambda: {
        "port": 8192, "profile_id": "flux", "install_root": str(tmp_path), "fingerprints": ["fixed"],
    })
    monkeypatch.setattr(service, "_target", lambda ident: (8192, "http://127.0.0.1:8192"))
    monkeypatch.setattr(service, "_launcher", lambda folder: (tmp_path, tmp_path / "python.exe",
                                                            tmp_path / "main.py", ["fixed"]))
    monkeypatch.setattr(service, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ops_control, "require_active", lambda: None)
    monkeypatch.setattr(service.draft_resources, "snapshot", lambda: {})
    monkeypatch.setattr(service.draft_resources, "pressure", lambda sample, stage: None)
    monkeypatch.setattr(service, "_occupied", lambda port: service._owned())
    monkeypatch.setattr(service, "_probe", lambda port: {"devices": []} if service._owned() else None)
    monkeypatch.setattr(service, "_queue_busy", lambda port: False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0, raising=False)

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

    monkeypatch.setattr(subprocess, "Popen", Child)
    return children


def test_lifecycle(runtime):
    assert service.status()["state"] == "STOPPED"
    started = service.control("start")
    assert (started["state"], started["managed"], started["pid"]) == ("RUNNING", True, 1)
    assert service.control("restart")["pid"] == 2
    assert runtime[0].code == 0
    assert service.control("stop")["state"] == "STOPPED"
    assert runtime[1].code == 0


def test_external_comfy_is_never_adopted_or_stopped(runtime, monkeypatch):
    monkeypatch.setattr(service, "_probe", lambda port: {"devices": []})
    monkeypatch.setattr(service, "_occupied", lambda port: True)
    assert service.ensure_running(8192)
    status = service.status()
    assert status["state"] == "RUNNING"
    assert status["pid"] is None and not status["managed"]
    for action in ("stop", "restart"):
        with pytest.raises(PermissionError, match="did not launch"):
            service.control(action)
    assert not runtime


def test_refuse_stop_during_production_or_provider_work(runtime, monkeypatch):
    service.control("start")
    monkeypatch.setattr(draft_pipeline, "ACTIVE", "production")
    with pytest.raises(PermissionError, match="production"):
        service.control("stop")
    monkeypatch.setattr(draft_pipeline, "ACTIVE", None)
    monkeypatch.setattr(service, "_queue_busy", lambda port: True)
    assert service.status()["busy"]
    with pytest.raises(PermissionError, match="queue"):
        service.control("restart")
    assert len(runtime) == 1 and runtime[0].code is None


def test_start_admission_respects_memory(runtime, monkeypatch):
    monkeypatch.setattr(service.draft_resources, "pressure", lambda sample, stage: "COMMIT_LOW")
    with pytest.raises(service.StartupPressure, match="COMMIT_LOW"):
        service.ensure_running(8192)
    assert not runtime


def test_other_comfy_process_blocks_duplicate_even_on_a_different_port(runtime, monkeypatch):
    monkeypatch.setattr(service.draft_resources, "snapshot", lambda: {
        "processes": {"comfyui": [{"pid": 987}]},
    })
    with pytest.raises(ValueError, match="Another ComfyUI process"):
        service.ensure_running(8192)
    assert not runtime


def test_startup_timeout_and_crash_recovery(runtime, monkeypatch):
    with monkeypatch.context() as timing:
        timing.setattr(service, "_probe", lambda port: None)
        timing.setattr(service, "START_TIMEOUT", 0)
        with pytest.raises(ValueError, match="timed out"):
            service.ensure_running(8192)
        with pytest.raises(ValueError, match="startup was skipped"):
            service.ensure_running(8192)
        assert service.status()["state"] == "ERROR"
        assert len(runtime) == 1
        runtime[0].code = 1
    assert service.control("start")["pid"] == 2


def test_concurrent_automatic_requests_share_process(runtime, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def probe(port):
        if service._owned():
            entered.set()
            assert release.wait(5)
            return {"devices": []}
        return None

    monkeypatch.setattr(service, "_probe", probe)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(service.ensure_running, 8192)
        assert entered.wait(5)
        assert service.status()["state"] == "STARTING"
        second = pool.submit(service.ensure_running, 8192)
        release.set()
        assert first.result(timeout=5)
        assert second.result(timeout=5)
    assert len(runtime) == 1


@pytest.mark.skipif(os.name != "nt", reason="Portable launcher registration is Windows-only")
def test_registration_pins_fixed_files_in_sqlite(monkeypatch, tmp_path):
    monkeypatch.setattr(model_hub, "DB_PATH", tmp_path / "hub.sqlite3")
    monkeypatch.setattr(service, "_target", lambda ident: (8192, "http://127.0.0.1:8192"))
    monkeypatch.setattr(service, "_probe", lambda port: None)
    monkeypatch.setattr(service, "_occupied", lambda port: False)
    monkeypatch.setattr(service, "_CHILD", None)
    with pytest.raises(ValueError, match="could not be read"):
        service.configure("flux", str(tmp_path))
    exe = tmp_path / "python_embeded" / "python.exe"
    script = tmp_path / "ComfyUI" / "main.py"
    for path, body in [(exe, b"MZ binary"), (script, b"import comfy.cli_args")]:
        path.parent.mkdir()
        path.write_bytes(body)
    assert service.configure("flux", str(tmp_path))["profile_id"] == "flux"
    assert service._settings()["install_root"] == str(tmp_path)
    script.write_bytes(b"import comfy.cli_args # changed")
    monkeypatch.setattr(ops_control, "require_active", lambda: None)
    monkeypatch.setattr(service.draft_resources, "pressure", lambda sample, stage: None)
    monkeypatch.setattr(service.draft_resources, "snapshot", lambda: {})
    with pytest.raises(ValueError, match="files changed"):
        service.ensure_running(8192)
