# Workflow runtime follow-up after PR #125

Baseline `origin/main` at `1661401`. Work branch
`feat/agentforge-workflow-runtime`. Verdict **NO-GO** for full production
readiness. This report distinguishes remaining implementation from environment
and Owner verification blockers.

## Delivered and remaining

| Area | Status | Change, evidence and limitation |
|---|---|---|
| Composed Goal execution | DONE | `5a76a4e`, `a0576d0` in `core/brain_planner.py` and `brain_runner.py`. Up to six reviewed steps using existing trusted schemas. Separate grants per step. Exact prior diagnostic stdout can feed a subsequent report. Real HTTP/SQLite/process/filesystem scenario in `tests/test_workflow_composition.py`. |
| General agent loop | PARTIAL | `7dc71da` in `core/brain_planner.py`, `api/routes/workspace.py` and Workspace. One approved local call can draft typed multi-tool plans. Invalid intents are rejected before tool dispatch. Arbitrary result-driven replanning, generalized output binding and per-tool checkpoints remain unimplemented. |
| Ollama planner acceptance | BLOCKED | No Ollama service returned metadata on host preflight. Model outputs in the new integration tests are fixtures. |
| Filesystem | PARTIAL | `743fef1` adds new versions from a rejected report, verifies source SHA again at execution and uses anchored report readback where supported. No generic text edit/patch or Windows junction-race certification. |
| Terminal | PARTIAL | Existing fixed Python diagnostic exercised inside the new composed workflow using a real process. Generic allowlisted command execution and process-tree cancellation remain unimplemented. |
| Browser and Git tools | PARTIAL | Existing offline generated-app QA remains available. The general browser-action surface and Git tool have not been added. |
| HTTP and research | PARTIAL | `2d5470e` in `source_reader.py` pins vetted public DNS results, rejects mixed private/public answers before connect, preserves TLS hostname verification and bypasses proxies and redirects. Fault-injection transport tests run locally. Generic authenticated HTTP tooling remains open. |
| Capability routing and model readiness | PARTIAL | `37744e4` in `ai/model_health.py` aligns scoped checks and actual local inference policy, exposes route origin and keeps catalog membership separate from loadability. No hardware-based selection or fallback. |
| Task cancellation | PARTIAL | `fb3a649`, `c130cb2` in Goal and task stores and runner. Exact SHA/revision cancellation before execution or while awaiting approval. Completed effects retained. Child resume is gated by the active parent. Recovery reconciles the task-store write after injected failure with no replay. In-flight interruption and in-skill checkpoints remain unimplemented. |
| Report revision and Owner review | DONE | `743fef1`. Real HTTP integration exercises reject, submit changed text, create new approved version, confirm source bytes persist, and accept replacement. This is an Owner-edited report flow. Automatic revision from feedback and actual Owner runtime acceptance remain open. |
| Dashboard | PARTIAL | `fb3a649`, `743fef1`, `7dc71da`, `37744e4`. Existing Workspace gains planning, cancellation, report revision and capability evidence. Local navigation regression and production build run. Expanded product timeline, mobile and a11y review remain open. |
| Website and React Builder | BLOCKED | Novel generated-app live validation requires a model and Docker. Chromium launch was refused in the Linux environment. NovaMart reference tests and build passed. No builder feature expansion in this branch. |
| Image and video | BLOCKED | Preflight returned ComfyUI/GPU unavailable. Disposable FFmpeg audio/video encode/decode ran. AI image/motion quality remains unverified. |
| Business automation | PARTIAL | No new live integrations in this branch. Existing orders/dispatch logic does not establish live acceptance with service accounts. Such tests require Owner-controlled credentials and permission. |
| Security and E2E | PARTIAL | Reviewed this branch for policy bypass, cancellation failure, stale SHA, and DNS rebinding. Focused adversarial tests reproduced relevant denial paths. Repository-wide threat-suite and live provider E2E remain open. |

## Results

Linux Python regression completed with 1,080 passed and zero failures or
skips. Dashboard passed 41 navigation tests and its production build.
NovaMart passed seven tests and its production build. Dashboard Vite emitted
a bundle-size warning. The full scope remains incomplete.

## Verification commands

- `python -m unittest discover -s tests -q` on Linux with Python 3.13 and
  repository media dependencies.
- `npm run test:navigation` and `npm run build` in `dashboard`.
- `npm test` and `npm run build` in `templates/novamart`.
- `python scripts/check_source_hygiene.py`, `python scripts/check_docs.py`,
  `python scripts/compat_audit.py --check`, and `git diff --check`.
- `python -m agentforge.ops.runtime_certification --run-ffmpeg --confirm-local-exec`.
  Runtime reported Ollama, ComfyUI and Docker `UNAVAILABLE` and
  `ffmpeg_encode_decode: PASS_RUNTIME`.
- `AGENTFORGE_BROWSER_EXECUTABLE=/usr/bin/chromium npm run test:browser`
  attempted from Dashboard. Chromium returned `socket() failed: Operation
  not permitted` before navigation. Windows CI is tracked on the PR.

The test module `tests/test_workflow_composition.py` provides reproducible
local evidence. HTTP sessions, SQLite, subprocess output and artifact bytes
are real. Its local model answer is a fixture. Fault injection checks the
Goal commit followed by a failed write to task history and verifies explicit
recovery twice. Live model acceptance, benchmark latency and workstation
verification are pending.

## Owner pilot on Windows

Follow the [Windows setup](../verification/OWNER_RUNTIME_ACCEPTANCE.md),
using this PR's branch and commit. Select an installed Ollama model for
Nghiên cứu cơ hội, enable the external-tools server mode, then in Workspace
pick **Dùng Ollama lập kế hoạch nhiều bước**. Try asking to check Python in
a disposable workspace directory and save the verified output in a new
Markdown report. Review planned arguments and SHA. Approve and independently
authorize each step. Compare the report bytes to the process receipt before
acceptance. Test rejection and replacement with a separate report.
