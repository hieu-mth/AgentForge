"""FLUX graph validation and visual job admission contracts."""
import copy
import io
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from agentforge.ai import model_hub, orchestrator_policy
from agentforge.features.media import flux_runtime, flux_workflow, visual_jobs


def profile():
    fields = {
        "6": {"text": "default", "clip": ["39", 0]},
        "8": {"samples": ["31", 0], "vae": ["40", 0]},
        "9": {"filename_prefix": "fixture", "images": ["8", 0]},
        "27": {"width": 768, "height": 768, "batch_size": 1},
        "31": {"seed": 1, "steps": 4, "cfg": 1, "sampler_name": "euler",
               "scheduler": "simple", "denoise": 1, "model": ["38", 0],
               "positive": ["6", 0], "negative": ["33", 0], "latent_image": ["27", 0]},
        "33": {"text": "", "clip": ["39", 0]},
        "38": {"unet_name": "fixture.gguf"},
        "39": {"clip_name1": "clip.safetensors", "clip_name2": "t5.safetensors", "type": "flux"},
        "40": {"vae_name": "vae.safetensors"},
    }
    graph = {key: {"class_type": flux_workflow.NODES[key][0], "inputs": inputs}
             for key, inputs in fields.items()}
    return {"id": "fixture_flux", "provider": "comfyui", "enabled": True,
            "model": "fixture.gguf", "base_url": "http://127.0.0.1:12345",
            "flux": {"workflow": graph, "max_resolution": 1024, "max_steps": 6,
                     "timeout_seconds": 5, "output_dir": "frames/flux"}}


class FluxRuntimeTests(unittest.TestCase):
    def test_registry_readiness_checks_non_loader_nodes_and_installed_weights(self):
        config = profile()["flux"]
        graph = config["workflow"]
        definitions = {node["class_type"]: {"input": {"required": {
            key: [[value]] for key, value in node["inputs"].items()
        }}} for node in graph.values()}

        def metadata(path, *, port, timeout=5):
            self.assertEqual(port, 12345)
            if path == "/system_stats":
                return {"devices": [{"type": "cuda"}]}
            kind = path.removeprefix("/object_info/")
            return {kind: definitions[kind]} if kind in definitions else {}

        with patch.object(flux_runtime, "_json", side_effect=metadata):
            self.assertEqual(flux_runtime.readiness(config, 12345, inspect_all_nodes=True), "READY")
            definitions["UnetLoaderGGUF"]["input"]["required"]["unet_name"] = [[]]
            self.assertEqual(flux_runtime.readiness(config, 12345, inspect_all_nodes=True), "MODEL_UNAVAILABLE")
            definitions.pop("KSampler")
            self.assertEqual(flux_runtime.readiness(config, 12345, inspect_all_nodes=True), "WORKFLOW_NODE_UNAVAILABLE")

    def setUp(self):
        self.enterContext(patch.object(flux_runtime.draft_resources, "require_gpu"))
        self.enterContext(patch.object(flux_runtime.comfy_service, "_settings", return_value=None))

    def test_workflow_limit_counts_utf8_bytes(self):
        row = profile()
        graph = row["flux"]["workflow"]
        graph["6"]["inputs"]["text"] = "🟠" * 2000
        graph["9"]["inputs"]["filename_prefix"] = "🟠" * 2000
        with self.assertRaisesRegex(ValueError, "byte limit"):
            model_hub.validate_profile(row)

    def test_graph_mapping_and_limits(self):
        cfg = model_hub.validate_profile(profile())["flux"]
        original = copy.deepcopy(cfg["workflow"])
        graph = flux_workflow.bind(cfg, "0" * 32, " new prompt ", 512, 768, 1234, 5)
        self.assertEqual(cfg["workflow"], original)
        expected = copy.deepcopy(original)
        expected["6"]["inputs"]["text"] = "new prompt"
        expected["27"]["inputs"].update(width=512, height=768)
        expected["31"]["inputs"].update(seed=1234, steps=5)
        expected["9"]["inputs"]["filename_prefix"] = "af_" + "0" * 32
        self.assertEqual(graph, expected)
        for w, h, s in ((257, 768, 4), (1536, 768, 4), (768, 768, 7)):
            with self.assertRaises(ValueError):
                flux_workflow.bind(cfg, "0" * 32, "image", w, h, 1, s)
        cfg["workflow"]["9"]["inputs"]["images"] = ["40", 0]
        with self.assertRaises(ValueError):
            model_hub.validate_profile(profile() | {"flux": cfg})

    def test_numbering_changes_preserve_bindings(self):
        row = profile()
        original = row["flux"]["workflow"]
        remapped = {key: str(int(key) + 100) for key in original}
        graph = {remapped[key]: {**node, "inputs": {
            name: [remapped[value[0]], value[1]] if isinstance(value, list) else value
            for name, value in node["inputs"].items()}} for key, node in original.items()}
        row["flux"]["workflow"] = graph
        config = model_hub.validate_profile(row)["flux"]
        bound = flux_workflow.bind(config, "a" * 32, "remapped", 512, 768, 24, 4)
        self.assertEqual(bound["106"]["inputs"]["text"], "remapped")
        self.assertEqual(bound["109"]["inputs"]["filename_prefix"], "af_" + "a" * 32)
        self.assertEqual(graph["106"]["inputs"]["text"], "default")
        graph["131"]["inputs"]["negative"] = ["106", 0]
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            model_hub.validate_profile(row)

    def test_output_location(self):
        for folder in ("C:/owner", "../outside", "frames/../outside", "frames/NUL", "/absolute"):
            value = profile()
            value["flux"]["output_dir"] = folder
            with self.subTest(folder=folder), self.assertRaises(ValueError):
                model_hub.validate_profile(value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            try:
                (workspace / "alias").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Directory symlink unavailable")
            with patch.object(flux_runtime, "WORKSPACE_DIR", workspace):
                with self.assertRaises(PermissionError):
                    flux_runtime.output_directory("alias/images")
            self.assertEqual(list(outside.iterdir()), [])

    def test_offline_timeout_missing_and_cancelled(self):
        with patch.object(flux_runtime, "_json", side_effect=ConnectionRefusedError):
            self.assertEqual(flux_runtime.readiness(profile()["flux"], 12345), "COMFYUI_UNAVAILABLE")
        with (patch.object(flux_runtime.time, "monotonic", side_effect=[0, 0, 6, 6]),
              patch.object(flux_runtime.time, "sleep"),
              patch.object(flux_runtime, "_json", return_value={})):
            with self.assertRaisesRegex(flux_runtime.JobError, "TIMED_OUT"):
                flux_runtime._collect("provider", "job", 12345, profile()["flux"], {})
        with self.assertRaisesRegex(flux_runtime.JobError, "OUTPUT_MISSING"):
            flux_runtime._output({"status": {"status_str": "success", "completed": True}}, "job", "109")
        with self.assertRaisesRegex(flux_runtime.JobError, "CANCELLED"):
            flux_runtime._output({"status": {"messages": [["execution_interrupted"]]}}, "job", "109")

    def test_profile_probe_without_route_auto_starts_before_submitting_and_collects_png(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Media extra unavailable")
        png = io.BytesIO()
        Image.new("RGB", (256, 256)).save(png, "PNG")
        pid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        calls = []
        filename = None

        def provider(path, **kwargs):
            nonlocal filename
            calls.append(path)
            if path == "/queue":
                return {"queue_running": [], "queue_pending": []}
            if path == "/prompt":
                self.assertEqual(calls[:2], ["start", "/queue"])
                filename = kwargs["body"]["prompt"]["9"]["inputs"]["filename_prefix"] + "_00001_.png"
                return {"prompt_id": pid}
            return {pid: {"status": {"status_str": "success", "completed": True},
                          "outputs": {"9": {"images": [
                              {"filename": filename, "subfolder": "", "type": "output"}]}}}}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hub, db = root / "hub.db", root / "visual.db"
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=profile(), db_path=hub)
            with (patch.object(flux_runtime, "WORKSPACE_DIR", root / "workspace"),
                  patch.object(flux_runtime, "readiness", side_effect=["COMFYUI_UNAVAILABLE", "READY"]),
                  patch.object(flux_runtime.comfy_service, "require_idle_queue") as alternate_queue,
                  patch.object(flux_runtime.comfy_service, "ensure_running",
                               side_effect=lambda port: calls.append("start")),
                  patch.object(flux_runtime, "_json", side_effect=provider),
                  patch.object(flux_runtime.comfyui, "request_image_bytes",
                               side_effect=lambda *args, sink, **kwargs: sink.write(png.getvalue()) and b"") as download):
                with self.assertRaisesRegex(ValueError, "REVISION_CONFLICT"):
                    flux_runtime.generate("probe", profile_id="fixture_flux", expected_revision=0,
                                          hub_db=hub, db_path=db)
                result = flux_runtime.generate("probe", profile_id="fixture_flux", expected_revision=1,
                                               width=256, height=256, seed=42, hub_db=hub, db_path=db)
                self.assertTrue(visual_jobs.report(db_path=db)["jobs"][0]["probe"])
                self.assertEqual(visual_jobs.image_for_job(result["job_id"], db_path=db)[0], png.getvalue())
                alternate_queue.assert_called_once_with(8188, allow_offline=True)
            self.assertEqual(calls, ["start", "/queue", "/prompt", "/history/" + pid])
            self.assertEqual(download.call_args.kwargs["max_response_bytes"], visual_jobs.MAX_IMAGE)
            self.assertEqual(result["status"], "ASSET_READY")
            self.assertEqual((root / result["workspace_path"]).read_bytes(), png.getvalue())

    def test_collection_reports_managed_process_exit(self):
        with (patch.object(flux_runtime, "_json", side_effect=ConnectionRefusedError),
              patch.object(flux_runtime.comfy_service, "managed_exited", return_value=True)):
            with self.assertRaisesRegex(flux_runtime.JobError, "COMFYUI_STOPPED"):
                flux_runtime._collect("provider-id", "a" * 32, 8188, profile()["flux"], {})

    def test_provider_host_buffer_error_has_resource_status(self):
        status = {"status_str": "error", "messages": [
            ["execution_error", {"exception_message": "HostBuffer.read_file_slice failed"}],
        ]}
        with self.assertRaisesRegex(flux_runtime.JobError, "GPU_RESOURCE_FAILURE"):
            flux_runtime._output({"status": status}, "a" * 32, "9")

    def test_owner_policy_and_concurrent_gpu_admission(self):
        try:
            import PIL
        except ImportError:
            self.skipTest("Media extra unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hub, db = root / "hub.db", root / "visual.db"
            model_hub.change("SAVE_MODEL_PROFILE", expected_revision=0, profile=profile(), db_path=hub)
            model_hub.change("SET_MODEL_ROUTE", expected_revision=1, task_id="image.generate",
                             model_ref="fixture_flux", db_path=hub)
            with self.assertRaises(PermissionError):
                model_hub.image_runtime(automated=True, db_path=hub)
            policy = orchestrator_policy.defaults()
            policy["permissions"].update(assign_models=True, call_local=True)
            model_hub.change("SAVE_ORCHESTRATOR", expected_revision=2, policy=policy, db_path=hub)
            dispatched, release = threading.Event(), threading.Event()
            calls = []

            def provider(path, **kwargs):
                calls.append(path)
                if path == "/queue":
                    return {"queue_running": [], "queue_pending": []}
                if path == "/prompt":
                    dispatched.set()
                    self.assertTrue(release.wait(5))
                    return {"prompt_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}
                raise AssertionError(path)

            with (patch.object(flux_runtime, "WORKSPACE_DIR", root / "workspace"),
                  patch.object(flux_runtime, "readiness", return_value="READY"),
                  patch.object(flux_runtime.comfy_service, "require_idle_queue") as alternate_queue,
                  patch.object(flux_runtime, "_json", side_effect=provider),
                  patch.object(flux_runtime, "_collect", side_effect=flux_runtime.JobError("OUTPUT_MISSING")),
                  ThreadPoolExecutor(max_workers=2) as pool):
                future = pool.submit(flux_runtime.generate, "first", automated=True, hub_db=hub, db_path=db)
                try:
                    if not dispatched.wait(3):
                        if future.done():
                            future.result()
                        self.fail("First visual job did not reach provider dispatch")
                    with self.assertRaisesRegex(PermissionError, "outstanding"):
                        flux_runtime.generate("second", automated=True, hub_db=hub, db_path=db)
                finally:
                    release.set()
                result = future.result(5)
                self.assertEqual(alternate_queue.call_count, 2)
                alternate_queue.assert_called_with(8188, allow_offline=True)
            self.assertEqual(calls, ["/queue", "/prompt"])
            self.assertEqual(result["status"], "OUTPUT_MISSING")
            self.assertEqual(visual_jobs.report(db_path=db)["jobs"][0]["prompt"], "first")
            self.assertEqual(list((root / "workspace").rglob("*.png")), [])
