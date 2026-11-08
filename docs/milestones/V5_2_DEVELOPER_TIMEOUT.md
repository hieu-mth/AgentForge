# V5.2 — AI Developer long-running inference (Owner screenshot)

## Observed failure

The Owner's V5 Goal stopped at `webapp.develop` with
`MODEL_TIMEOUT: AI Developer inference timed out.`. The prior gateway
gave all workers the same 180-second socket timeout. With Ollama
`stream: false`, a large React JSON response is not returned to the client
until the model finishes generating it. This can exceed 180 seconds on
local `qwen3:8b` hardware; cloud gateways can also need longer to return
up to 8,192 output tokens. The screenshot alone cannot establish whether
local inference speed, provider overload or a network stall caused this
specific run.

## Bounded changes

- **Developer-only local streaming:** Ollama structured-JSON generation
  now uses a *single* `/api/chat` call with `stream: true`, collects text
  chunks, and requires the final `done: true` event. Broken/invalid or
  oversized streams are rejected; incomplete source never gets a signed
  proposal. All other Ollama workers retain non-streaming responses.
- **Developer-only socket timeout:** default **600 seconds** for local
  Ollama and the configured cloud gateway. Override on the same machine
  using `AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS` (integer **60–900**).
  Other workers stay at **180 seconds**. This is a socket I/O timeout,
  not a hard end-to-end execution deadline or a guarantee of success.
- **Owner-safe diagnostics:** classify a timed-out Developer request,
  interrupted local stream, and excess response size without storing
  raw output, secrets or provider error messages.
- **No additional authority:** one approved call per Developer stage,
  no automatic retry, no automatic cloud fallback, no auto-install,
  no executable generated code, no re-running an already failed Goal.
  SHA lineage, deterministic static QA and the advisory Reviewer stay intact.

## Windows acceptance

Update from the merged commit:

```powershell
cd D:\AgentForge
git pull --ff-only origin main
# Optional: override the default 600-second Developer timeout
$env:AGENTFORGE_DEVELOPER_TIMEOUT_SECONDS = '900'
# Restart the Control Center from this same PowerShell session
```

Use your existing project startup command to restart the Control Center.
If you start it from another terminal, move the optional setting to the
project's local ignored `.env` instead. No UI build is required by this
backend-only patch.

In Owner Settings, confirm the V5 workspace cap allows **3 model calls**.
Ensure Ollama is running with the model assigned to `webapp_developer`,
or explicitly configure and consent to an allowed cloud model. Submit
a **new** scoped V5 Goal; approve Architect, Developer and Reviewer
individually. Check that Developer emits an SHA-bound React proposal,
static QA reports `PASS_STATIC_ONLY`, and Reviewer emits its advisory
report. A green Goal does *not* prove the app builds or renders; run
the separate approved offline Docker QA to check those properties.

## Regression coverage

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_v52_developer_streaming tests.test_ai_developer_diagnostics_v51 tests.test_v5_company -v
```

Fixture tests cover complete multi-chunk responses, truncated streams,
safe size limits, redaction, timeout configuration, a cloud response and
non-Developer compatibility. They do not benchmark an actual Ollama
model or the Owner's Windows hardware.
