# Windows Owner acceptance

The draft PR targets `main`. Review its diff and CI before testing a branch.
Commit the relevant SHA with the evidence. Use a disposable workspace scope
and keep any existing Owner configuration or artifacts.

```powershell
Set-Location D:\AgentForge
git status --short
git fetch origin main feat/agentforge-full-runtime
git switch --track origin/feat/agentforge-full-runtime
git rev-parse HEAD
ollama list
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd --prefix dashboard ci
npm.cmd --prefix dashboard run build
.\.venv\Scripts\python.exe -m agentforge --port 8780 --allow-external-tools
```

If the local branch already exists, switch to it and fast-forward it separately.
Create the Python 3.13 virtual environment if it is missing. Open
`http://127.0.0.1:8780/dashboard/` and log in as Owner.

1. In Model Hub select an enabled Ollama profile assigned to **Nghiên cứu cơ hội**.
   A process or `.env` value of `AGENTFORGE_MODEL_REF` overrides worker assignment.
   Use the local route for this workflow. Select **Chạy thử**, approve the fixed
   prompt and record the model name, revision, status and time. A successful
   result demonstrates a minimal completion only.
2. Create two disposable Markdown files in `workspace/owner-runtime-fixture`
   with different facts about a timeout and the restart procedure. Use a new
   scope if the example name already exists.
3. Set the Prompt Workspace budget to 3. Submit a brief such as
   “Đối chiếu quy định timeout và hướng dẫn xử lý trong
   workspace/owner-runtime-fixture. Nêu các khác biệt và dẫn tài liệu đã đọc.”
4. Inspect the Goal scope and SHA. Approve, grant the requested model and
   workspace write permissions, then run. Verify the observed read/search
   operations, citations, and output under `workspace/agent-reports/`. Preserve
   the Goal ID and receipt. If processing fails, record the first safe error.
5. Check the SHA with `Get-FileHash -Algorithm SHA256 <artifact-path>`.
   Review content against the source files before Owner acceptance.
6. Repeat with a different brief and fixture, and verify that the observed tool
   sequence responds to the evidence. Separately use a fresh Goal to weigh
   an incorrect report and record the Owner rejection. Revision linkage for
   this skill is pending.

For product runtime, use the existing [Owner production gate](OWNER_PRODUCTION_GATE.md)
and [Wave 8 media workflow](wave8/README.md). Record live calls and artifact
verification separately from CI. Sampling a model, decoding an MP4 or generating
a draft report alone leaves product quality unverified.
