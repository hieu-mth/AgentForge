"""V4.2b: experimental AI React source never executes on the Windows host."""
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agentforge import (
    brain_planner, brain_runner, brain_store, prompt_intake, task_history,
    webapp_builder, webapp_developer, webapp_sandbox,
)
from tests.test_webapp_revision_http_v41 import WebappRevisionHttpTests

DEV = webapp_developer
APP = """import React, {useState} from 'react';
export default function App(){
  const [count,setCount] = useState(0);
  return <main><h1>Cửa hàng demo</h1><button onClick={()=>setCount(count+1)}>
    Giỏ hàng {count}</button></main>;
}
"""
CSS = """body { margin: 0; font-family: Arial, sans-serif; }
main { max-width: 60rem; padding: 2rem; } button { cursor: pointer; }
"""
MODEL = {
    "title": "Cửa hàng React Demo",
    "summary": "Ứng dụng có giỏ hàng demo tăng số lượng bằng state React.",
    "files": [
        {"path": "src/App.jsx", "content": APP},
        {"path": "src/styles.css", "content": CSS},
    ],
}
BRIEF = "AI Developer: tạo web app React tùy biến kiểu Shopee, có giỏ hàng demo hoạt động thật."


class AIReactDeveloperTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for obj, field, value in (
            (DEV, "PROPOSALS", root / "dev-proposals"),
            (DEV, "PROJECTS", root / "projects"),
            (webapp_builder, "PROPOSALS", root / "webapp-proposals"),
            (webapp_builder, "PROJECTS", root / "projects"),
            (webapp_sandbox, "QA_STAGING", root / "staging"),
        ):
            p = patch.object(obj, field, value)
            p.start()
            self.addCleanup(p.stop)
        self.brain = root / "brain.sqlite3"
        self.tasks = root / "task.sqlite3"

    def propose(self, value=None, slug="custom-react"):
        with (patch("agentforge.model.generate_json",
                    return_value=MODEL if value is None else value) as model,
              patch("subprocess.run") as process):
            proposal = DEV.propose(slug, BRIEF)
            model.assert_called_once()
            self.assertEqual(model.call_args.args[1], DEV.CODE_SCHEMA)
            self.assertEqual(model.call_args.kwargs["worker_id"], "webapp_developer")
            process.assert_not_called()
        return proposal

    def test_code_worker_has_independent_instructions_from_static_designer(self):
        from agentforge.worker_registry import load_worker
        designer = load_worker("product_builder")
        developer = load_worker("webapp_developer")
        self.assertEqual(developer["model_ref"], designer["model_ref"])
        self.assertNotEqual(developer["instructions"], designer["instructions"])
        self.assertIn("React JSX", developer["instructions"])
        self.assertIn("propose_react_source_only", developer["capabilities"])

    def test_create_source_only_with_trusted_dependencies(self):
        receipt = self.propose()
        self.assertFalse(DEV.PROJECTS.exists())
        self.assertEqual(receipt["format"], DEV.FORMAT)
        doc, _ = DEV._read_proposal(receipt["proposal_id"])
        files = {x["path"]: x["content"] for x in doc["files"]}
        self.assertEqual(files["src/App.jsx"], APP)
        self.assertEqual(files["src/styles.css"], CSS)
        self.assertNotIn("node_modules", files)
        self.assertIn("package-lock.json", files)
        self.assertEqual(json.loads(files["package-lock.json"])["packages"][""]["devDependencies"],
                         json.loads(files["package.json"])["devDependencies"])
        self.assertIn("react", files["package.json"])
        self.assertIn("vite", files["package.json"])
        self.assertIn("readFileSync", files["tests/contract.test.js"])
        self.assertFalse(doc["execution_authorized"])
        self.assertFalse(doc["deployment_authorized"])
        self.assertIs(DEV.provider(receipt["proposal_id"]), DEV)
        self.assertIn("sha256", DEV.inspect(receipt["proposal_id"]))

    def test_rejects_unsafe_paths_imports_browser_apis_and_invalid_code(self):
        def changed(path, contents):
            spec = deepcopy(MODEL)
            spec["files"][0] = {"path": path, "content": contents}
            return spec
        cases = [
            changed("../parent.jsx", APP),
            changed("src/evil.js", APP),
            changed("src/App.jsx", "import mystery from 'axios';\n" + APP),
            changed("src/App.jsx", "import secret from './bad.js';\n" + APP),
            changed("src/App.jsx", "fetch('http://bad.invalid');\n" + APP),
            changed("src/App.jsx", "eval('alert(1)');\n" + APP),
            changed("src/App.jsx", "window.location = '/evil';\n" + APP),
            changed("src/App.jsx", "const x = import('./helpers.js');\n" + APP),
            changed("src/App.jsx", APP.replace("export default", "const identity =")),
            changed("src/App.jsx", APP.replace("import React", "import('secret');\nimport React")),
        ]
        css = deepcopy(MODEL)
        css["files"][1]["content"] += "@import 'https://other.invalid';"
        cases.append(css)
        missing = deepcopy(MODEL)
        missing["files"][0]["content"] = (
            "import Header from './components/Header.jsx';\n" + APP)
        cases.append(missing)
        for index, case in enumerate(cases):
            with self.subTest(case=index), patch("agentforge.model.generate_json",
                                                return_value=case) as model:
                with self.assertRaises(ValueError):
                    DEV.propose("custom-react", BRIEF)
                model.assert_called_once()
        self.assertFalse(DEV.PROPOSALS.exists())
        self.assertFalse(DEV.PROJECTS.exists())

    def test_all_eight_allowed_source_files_pass_review(self):
        expanded = deepcopy(MODEL)
        sources = expanded["files"]
        sources.extend([
            {"path": "src/data.js", "content": "export const PRODUCTS = [{id: 'p1'}];"},
            {"path": "src/helpers.js", "content": "export function total(items){return items.length;}"},
        ])
        for name in ("Header", "ProductCard", "Sidebar", "Modal"):
            sources.append({"path": "src/components/" + name + ".jsx",
                            "content": "import React from 'react';\n"
                                       + "export default function " + name
                                       + "(){return <section>Demo</section>;} "})
        receipt = self.propose(expanded)
        doc, _ = DEV._read_proposal(receipt["proposal_id"])
        self.assertEqual(len(doc["files"]), 15)  # Includes the reviewed dependency lock.

    def test_signed_integrity_prevents_changed_source_and_approval_required(self):
        receipt = self.propose()
        with patch("subprocess.run") as process:
            with self.assertRaises(PermissionError):
                DEV.apply(receipt["proposal_id"], sha256=receipt["sha256"])
            with self.assertRaises(PermissionError):
                DEV.apply(receipt["proposal_id"], sha256="0"*64, confirm_write=True)
            process.assert_not_called()
        path = Path(receipt["proposal_path"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["files"][0]["content"] += "tampered"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            DEV._read_proposal(receipt["proposal_id"])
        self.assertFalse(DEV.PROJECTS.exists())

    def test_forged_local_digest_cannot_replace_trusted_package_scripts(self):
        receipt = self.propose()
        path = Path(receipt["proposal_path"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        package = next(item for item in doc["files"] if item["path"] == "package.json")
        content = json.loads(package["content"])
        content["scripts"]["postinstall"] = "node -e 'process.exit(1)'"
        package["content"] = json.dumps(content, ensure_ascii=False)
        doc["sha256"] = DEV._digest(doc["project_slug"], doc["brief"],
                                     doc["title"], doc["summary"], doc["files"])
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "trusted project files"):
            DEV._read_proposal(receipt["proposal_id"])
        self.assertFalse(DEV.PROJECTS.exists())

    def test_manual_apply_only_writes_without_running_npm_or_overwriting(self):
        receipt = self.propose()
        with patch("subprocess.run") as process:
            applied = DEV.apply(receipt["proposal_id"],
                                sha256=receipt["sha256"], confirm_write=True)
            process.assert_not_called()
        self.assertEqual(applied["status"], "FILES_WRITTEN_NOT_EXECUTED")
        self.assertTrue((DEV.PROJECTS / "custom-react" / "src" / "App.jsx").is_file())
        with self.assertRaises(FileExistsError):
            DEV.apply(receipt["proposal_id"],
                      sha256=receipt["sha256"], confirm_write=True)

    def test_explicit_prompt_goes_to_distinct_one_call_goal_without_process_run(self):
        with patch("agentforge.workspace_policy.read", return_value={
            "website_enabled": True, "max_estimated_model_calls": 1,
        }), patch("agentforge.goal_preflight.require_ready"):
            planned = prompt_intake.plan_request(
                BRIEF, max_model_calls=1, brain_db_path=self.brain)
        self.assertEqual(planned["template"], "webapp.develop")
        goal = brain_store.get_goal(planned["goal_id"], db_path=self.brain)
        self.assertEqual(goal["plan"][0]["skill_id"], "webapp.develop")
        self.assertEqual(goal["plan"][0]["estimated_model_calls"], 1)
        self.assertNotIn("process.run", goal["plan"][0]["required_permissions"])
        brain_store.approve_goal(goal["goal_id"], goal["plan_sha256"],
                                db_path=self.brain)
        with patch("agentforge.model.generate_json") as model:
            waiting = brain_runner.execute(
                goal["goal_id"], brain_db_path=self.brain, task_db_path=self.tasks)
            model.assert_not_called()
        self.assertEqual(waiting["status"], "WAITING_APPROVAL")
        with patch("agentforge.model.generate_json", return_value=MODEL) as model:
            done = brain_runner.execute(
                goal["goal_id"], brain_db_path=self.brain, task_db_path=self.tasks,
                grants=("model.invoke", "workspace.propose"),
                confirm_model_call=True)
            model.assert_called_once()
        self.assertEqual(done["status"], "SUCCEEDED", done)
        step = brain_store.get_goal(goal["goal_id"], db_path=self.brain)["steps"][0]
        task = task_history.get_task(step["child_task_id"], db_path=self.tasks)
        self.assertEqual(task["result"]["format"], DEV.FORMAT)
        self.assertFalse(DEV.PROJECTS.exists())

    def test_sandbox_may_read_signed_ai_source_only_with_explicit_approval(self):
        receipt = self.propose()
        with patch("subprocess.run") as process:
            with self.assertRaisesRegex(PermissionError, "SANDBOX_APPROVAL_REQUIRED"):
                webapp_sandbox.verify(receipt["proposal_id"], receipt["sha256"])
            process.assert_not_called()
        with patch.dict("os.environ", {"AGENTFORGE_SANDBOX_IMAGE": ""}):
            with patch("subprocess.run") as process:
                with self.assertRaisesRegex(RuntimeError, "SANDBOX_UNAVAILABLE"):
                    webapp_sandbox.verify(receipt["proposal_id"], receipt["sha256"],
                                          confirm_external_run=True)
                process.assert_not_called()


class AIReactHttpTests(unittest.TestCase):
    # Reuse the real authenticated local HTTP transport without re-running
    # its baseline webapp-specific tests.
    setUp = WebappRevisionHttpTests.setUp
    req = WebappRevisionHttpTests.req
    login = WebappRevisionHttpTests.login
    _shutdown = WebappRevisionHttpTests._shutdown

    def test_ai_source_review_apply_and_revision_disabled(self):
        root = webapp_builder.PROPOSALS.parent
        patches = [
            patch.object(DEV, "PROPOSALS", root / "ai-proposals"),
            patch.object(DEV, "PROJECTS", webapp_builder.PROJECTS),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with patch("agentforge.model.generate_json", return_value=MODEL):
            receipt = DEV.propose("custom-ai-source", BRIEF)
        pid, sha = receipt["proposal_id"], receipt["sha256"]
        code, _, _ = self.req("GET", "/api/webapps/"+pid)
        self.assertEqual(code, 401)
        self.login()
        code, doc, _ = self.req("GET", "/api/webapps/"+pid)
        self.assertEqual(code, 200, doc)
        self.assertTrue(doc["ai_code_experimental"])
        self.assertEqual(doc["format"], DEV.FORMAT)
        self.assertFalse(doc["execution_authorized"])
        self.assertTrue(any(f["path"] == "src/App.jsx" for f in doc["files"]))
        code, _, _ = self.req("POST", "/api/webapps/"+pid+"/revision", {
            "ack": "REQUEST_REVISION", "sha256": sha,
            "feedback": "Đổi bố cục trang mua sắm theo yêu cầu."})
        self.assertEqual(code, 400)
        self.assertFalse((DEV.PROJECTS / "custom-ai-source").exists())
        code, response, _ = self.req("POST", "/api/webapps/"+pid+"/apply", {
            "ack": "APPLY_WEBAPP", "sha256": sha})
        self.assertEqual(code, 200, response)
        self.assertEqual(response["status"], "FILES_WRITTEN_NOT_EXECUTED")


if __name__ == "__main__":
    unittest.main()
