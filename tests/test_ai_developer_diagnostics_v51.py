"""Regression: real AI Developer failure codes and full-role V5 routing."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from agentforge import brain_store, model, prompt_intake, skill_runner


class AIModelFailureDiagnosticsTests(unittest.TestCase):
    def test_model_output_errors_have_actionable_redacted_categories(self):
        private="sk-test-NEVER-STORE private-response"
        cases=[
            (RuntimeError("Gateway response stopped at max_tokens ("+private+")"),"MODEL_OUTPUT_LIMIT"),
            (RuntimeError("Gateway returned no text content ("+private+")"),"MODEL_EMPTY_OUTPUT"),
            (RuntimeError("Gateway response has no content blocks ("+private+")"),"MODEL_EMPTY_OUTPUT"),
            (RuntimeError("Ollama returned an empty answer"),"MODEL_EMPTY_OUTPUT"),
            (RuntimeError("Model did not return a JSON object"),"MODEL_JSON_OBJECT_REQUIRED"),
            (RuntimeError(private),"MODEL_RUNTIME_FAILED"),
            (json.JSONDecodeError(private,"",0),"APP_CODE_JSON_INVALID"),
            (ValueError("title too long "+private),"APP_CODE_CONTRACT_INVALID"),
            (ValueError("APP_CODE_INVALID: invalid file path "+private),"APP_CODE_INVALID"),
            (ValueError("APP_CODE_UNSAFE: browser API "+private),"APP_CODE_UNSAFE"),
            (PermissionError("CLOUD_MODEL_CONSENT_REQUIRED "+private),"MODEL_PERMISSION_DENIED"),
            (HTTPError("https://secret.invalid",429,private,None,None),"MODEL_RATE_LIMITED"),
            (OSError(private),"APP_LOCAL_IO_FAILED"),
            (KeyError(private),"APP_CODE_INTERNAL"),
        ]
        for exc, expected in cases:
            with self.subTest(expected=expected,klass=type(exc).__name__):
                safe=skill_runner._safe_failure("webapp.develop",exc)
                self.assertTrue(safe.startswith(expected+":"),safe)
                self.assertNotIn(private,safe)
                self.assertLessEqual(len(safe),240)

    def test_cloud_react_json_budget_is_eight_k_not_four_and_no_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            env={
                "AGENTFORGE_MODEL_REF":"cloud_primary",
                "AGENTFORGE_CLOUD_MODEL_CONSENT":"YES",
                "ANTHROPIC_BASE_URL":"https://gateway.example/v1",
                "ANTHROPIC_AUTH_TOKEN":"dummy-private-token",
            }
            body={"stop_reason":"end_turn",
                  "content":[{"type":"text","text":'{"ok":true}'}]}
            with patch.dict(os.environ,env), \
                 patch.object(model,"DOTENV_PATH",Path(temp)/"missing.env"), \
                 patch.object(model, "_cloud_open",
                              return_value=io.BytesIO(json.dumps(body).encode())) as send:
                result=model.generate_json("Write a React app",{"type":"object"},
                                           worker_id="webapp_developer")
            self.assertEqual(result,{"ok":True})
            request=json.loads(send.call_args.args[0].data)
            self.assertEqual(request["max_tokens"],8192)
            self.assertEqual(send.call_count,1)
            self.assertNotIn("dummy-private-token",json.dumps(request))

    def test_developer_budget_explicit_opt_in_is_bounded(self):
        runtime={"system_prompt":"Trusted","model":"test",
                 "base_url":"https://gateway.example","api_key":"private"}
        for configured, expected in (("",8192),("12288",12288),("16384",16384)):
            with self.subTest(configured=configured), \
                 patch.dict(os.environ, {"AGENTFORGE_DEVELOPER_MAX_TOKENS":configured}), \
                 patch.object(model, "_cloud_open",
                              return_value=io.BytesIO(json.dumps({
                                  "stop_reason":"end_turn",
                                  "content":[{"type":"text","text":'{"ok":true}'}]
                              }).encode())) as send:
                model._anthropic_chat(runtime,"Generate JSON",{"type":"object"},
                                      worker_id="webapp_developer")
                payload=json.loads(send.call_args.args[0].data)
                self.assertEqual(payload["max_tokens"],expected)
                send.assert_called_once()
        for invalid in ("8191","16385","unlimited","-1"):
            with self.subTest(invalid=invalid), \
                 patch.dict(os.environ, {"AGENTFORGE_DEVELOPER_MAX_TOKENS":invalid}):
                with self.assertRaises(model.ModelConfigError):
                    model._developer_cloud_max_tokens()

    def test_older_json_worker_budget_stays_four_k(self):
        runtime={"system_prompt":"Trusted","model":"test",
                 "base_url":"https://gateway.example","api_key":"not-leaked"}
        raw=io.BytesIO(json.dumps({
            "content":[{"type":"text","text":'{"ok":1}'}],
            "stop_reason":"end_turn"}).encode())
        with patch.object(model, "_cloud_open",return_value=raw) as send:
            result=model._anthropic_chat(runtime,"Prompt",{"type":"object"},
                                         worker_id="product_builder")
        self.assertEqual(json.loads(result),{"ok":1})
        self.assertEqual(json.loads(send.call_args.args[0].data)["max_tokens"],4096)


class RetiredWebappIntakeTests(unittest.TestCase):
    def test_webapp_request_is_refused_before_goal_or_model_call(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "goals.db"
        prompt = ("Tạo ứng dụng React bán hàng, yêu cầu AI Architect, "
                  "AI Developer, QA kiểm tra mã và AI Reviewer phản biện.")
        with patch("agentforge.workspace_policy.read", return_value={
            "website_enabled": True, "storyboard_enabled": True,
            "max_estimated_model_calls": 3}), \
             patch("agentforge.model.generate_json") as model_call:
            with self.assertRaises(PermissionError):
                prompt_intake.plan_request(
                    prompt, max_model_calls=3, brain_db_path=db)
            model_call.assert_not_called()
        self.assertFalse(db.exists())


if __name__ == "__main__":
    unittest.main()
