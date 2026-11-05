"""V2.2 safe workspace inventory and no-generation model readiness regression."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import artifact_catalog, model_health


class _LocalResponse:
    status = 200

    def __init__(self, obj):
        self.data = json.dumps(obj).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, count):
        return self.data[:count]


class ArtifactCatalogTests(unittest.TestCase):
    def test_inventory_does_not_delete_or_read_file_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products, proposals, media = (root / x for x in
                                          ("products", "proposals", "media"))
            project = products / "nem-ngu"
            project.mkdir(parents=True)
            (project / "index.html").write_text("<html>test</html>", encoding="utf-8")
            proposals.mkdir()
            (proposals / ("a" * 32 + ".json")).write_text("private", encoding="utf-8")
            media_run = media / ("b" * 32)
            media_run.mkdir(parents=True)
            (media_run / "manifest.json").write_text('{"test":true}', encoding="utf-8")
            report = artifact_catalog.report(products=products, proposals=proposals,
                                             media=media)
            self.assertEqual(3, report["total_items"])
            self.assertEqual({"website", "proposal", "media"},
                             {x["kind"] for x in report["items"]})
            self.assertFalse(any("private" in json.dumps(x) for x in report["items"]))
            self.assertEqual(0, report["deleted"])
            self.assertFalse(any(x["deployed"] for x in report["items"]))
            self.assertTrue((project / "index.html").exists())
            with self.assertRaises(ValueError):
                artifact_catalog.report(products=products, proposals=proposals,
                                        media=media, limit=100000)

    def test_inventory_empty_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = artifact_catalog.report(products=root / "none",
                                             proposals=root / "none2",
                                             media=root / "none3")
            self.assertEqual([], report["items"])


class LocalModelHealthTests(unittest.TestCase):
    def _runtime(self, endpoint="http://127.0.0.1:11434"):
        return {"provider": "ollama", "base_url": endpoint, "model": "qwen3:8b"}

    def test_probe_only_requests_tags(self):
        calls = []
        def fetch(request, timeout):
            calls.append((request.get_method(), request.full_url, timeout))
            return _LocalResponse({"models": [{"name": "qwen3:8b"}]})
        result = model_health.check(resolve=lambda *_: self._runtime(), opener=fetch)
        self.assertEqual("READY", result["status"])
        self.assertFalse(result["generation_invoked"])
        self.assertEqual([("GET", "http://127.0.0.1:11434/api/tags", 3)], calls)

    def test_missing_model_and_remote_urls(self):
        for url in ("https://remote.example:443", "http://192.0.2.1:11434",
                    "http://127.0.0.1:11434/other", "http://127.0.0.1"):
            def deny(*_args, **_kwargs):
                raise AssertionError("Unexpected network call")
            result = model_health.check(resolve=lambda *_: self._runtime(url),
                                        opener=deny)
            self.assertEqual("INVALID_ENDPOINT", result["status"])
        missing = model_health.check(
            resolve=lambda *_: self._runtime(),
            opener=lambda *_a, **_k: _LocalResponse({"models": []}))
        self.assertEqual("MODEL_NOT_INSTALLED", missing["status"])

    def test_unavailable_is_sanitized(self):
        def fail(*_args, **_kwargs):
            raise TimeoutError("DO_NOT_EXPOSE_PROMPT_OR_HOST")
        result = model_health.check(resolve=lambda *_: self._runtime(), opener=fail)
        self.assertEqual("UNAVAILABLE", result["status"])
        self.assertNotIn("DO_NOT_EXPOSE", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
