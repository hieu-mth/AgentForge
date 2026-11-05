# V2.2 — Owner workflow, model health and local artifact management

## What changed

- **Giao việc** remains the main UI when a prompt turns into a bounded S4 plan. Owner sees the generated plan, SHA, required grants and APPROVE/RUN buttons in one screen. No model call is performed by prompt intake.
- **Kiểm tra Ollama** does a read-only GET to the configured loopback Ollama \`/api/tags\`. It will not load/generate model text or verify the resulting HTML quality. Status \`READY\` only means the endpoint responds and model is listed. No remote hosts are probed.
- **Projects & Files** shows a bounded, read-only list of local product roots, proposals and media run manifests. It does not serve file contents, delete, publish, or assert external deployment. File names and bytes may be listed only in the authenticated owner session.
- Existing owner permissions, session CSRF, task/audit records, external-action gate, per-call consent and product SHA review remain unchanged.

## On Windows PowerShell

After the PR is merged and the existing Control Center is stopped:

    cd D:\AgentForge
    git status --short
    git switch main
    git pull --ff-only origin main
    .\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780 --allow-external-tools

The flag allows **individual later owner approvals** to request a model; it does not run one by itself. The selected model, such as Ollama \`qwen3:8b\`, must already be installed and the Ollama service available.

Use the dashboard:
1. Sign in with the newly displayed owner code.
2. **Giao việc** → click **Kiểm tra Ollama**. If READY, prompt for a website. A plan is prepared locally.
3. Inspect plan/permissions and approve its SHA; to run, explicitly grant \`model.invoke\` and \`workspace.propose\` and confirm the model call. There is no model billing cap guaranteed by this standalone S4 call. If it fails, inspect sanitized error code in Task History.
4. **Websites** → open a successful proposal and inspect the source before any apply. Product Builder produces HTML with SVG illustration; **it does not generate photorealistic model images**.
5. **Projects & Files** → see existing local files and inventory. It will not delete business assets.

## Expected errors and safety

- \`MODEL_TIMEOUT\`: Ollama took too long during an actual generation request.
- \`HTML_INCOMPLETE\`, \`HTML_TOO_LARGE\`, \`HTML_QUALITY_FAILED\`: Model produced an unsupported or rejected HTML document.
- No silent automatic retries, and the old failed Task History remains immutable.
- A green CI does not confirm UX beauty, codec/image generation quality, a working public website, verified lead conversion or profit.

## Repository policy

See \`docs/architecture/REPOSITORY_STRUCTURE.md\`: \`src/agentforge\` is code; \`skills/\` is declarative; \`tests/\` contains regressions; \`data/\` and \`workspace/\` are local gitignored business output. Runtime artifacts are never deleted by this feature. Cache cleanup remains a separate opt-in operation.
