# Owner Operations V1.2 — emergency pause and attention queue

**Purpose:** operational control and safety for a single owner on the same
Windows computer. Builds on S1–S5 + Control Center V1.1. This is not a remote
multi-tenant service or a cloud process supervisor.

## What is now implemented

- Persistent, local, owner-controlled \`data/company/ops_control.json\`
  (gitignored); owner explicitly sets \`PAUSED\` or \`ACTIVE\`. Corruption,
  invalid format or unsafe symlink/junction pauses **fail closed**.
- Policy checks prevent NEW S1 skill invocations/resumes, S4 Goal execution
  and subsequent S4 step dispatch, and new S4 read-only schedule claims
  while paused. A paused foreground scheduler writes a \`PAUSED\` heartbeat
  and does not repeatedly emit a runtime failure.
- Authenticated owner-only \`POST /api/ops/control\`, with CSRF+Origin+Host
  enforcement already present in Control Center. Payload requires exact
  acknowledgement: \`{"mode":"PAUSED","ack":"PAUSE_OPERATIONS"}\` or
  \`{"mode":"ACTIVE","ack":"RESUME_OPERATIONS"}\`.
- Control Center Overview shows current state and a pause/resume control
  with a separate owner confirmation. It shows a bounded **Cần owner xử lý**
  inbox for pending approval, failed/interrupted Goals, interrupted tasks,
  or active schedules whose daemon heartbeat is stale.
- Operations Doctor reports whether the owner has paused dispatch.
  There is no new SQLite schema, background privilege escalation or network
  dependency.

## Honest kill-switch boundary

The pause flag is checked **before dispatch** and **between** bounded
Goal steps, not by a remote operating-system sandbox. A subprocess, browser
or model request that is already executing may finish or fail; it cannot be
forcibly terminated without risk of corrupting outputs or leaving ambiguous
external side effects. A Goal interrupted between steps is *not* replayed
automatically. The owner must inspect and create a new plan if necessary.

A separate CLI invoking an old legacy tool directly (bypassing S1) is
outside the S1 dispatch gate. This is an operational control for the unified
Company Brain/S1 route, not a machine-wide firewall or proof of financial
limits. Owner-approved manual record edits or draft planning can still
proceed while paused; dispatch is what stops.

## One-pass Windows acceptance

Stop the old Control Center with Ctrl+C; then:

\`\`\`powershell
cd D:\AgentForge
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Regression tests failed" }
.\.venv\Scripts\python.exe -m agentforge.ops_control status
.\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780
\`\`\`

Log in using the **fresh local owner code**. Open Overview. Press
**Tạm dừng hệ thống** and confirm. Operations should show \`PAUSED\`.
An APPROVED Goal run must be blocked; no new task should start.
Press **Tiếp tục vận hành**, confirm, refresh and verify \`ACTIVE\`.
Resume does *not* automatically restart old failures or schedules.

For emergency CLI operation without a browser:

\`\`\`powershell
.\.venv\Scripts\python.exe -m agentforge.ops_control pause --confirm-pause
.\.venv\Scripts\python.exe -m agentforge.ops_control status
.\.venv\Scripts\python.exe -m agentforge.ops_doctor
# Only when ready to allow new dispatch:
.\.venv\Scripts\python.exe -m agentforge.ops_control resume --confirm-resume
\`\`\`

There is no always-on service installed; restarting the foreground
read-only scheduler remains an owner action:

\`\`\`powershell
.\.venv\Scripts\python.exe -m agentforge.ops_daemon run --confirm-unattended --interval 60
\`\`\`

A machine that is off cannot process tasks, and local data/backups remain
unencrypted until the owner chooses a secure storage solution.

## What is still required for fully autonomous production

- Scoped legitimate YouTube/TikTok platform API credentials, review of
  permissions, consent, revocation and authenticated publish receipts.
- Server-side idempotency before external account actions and a tested
  fail-closed spend controller at each provider/tool boundary.
- Real consented lead handoff and sales CRM, actual tax/refund/affiliate
  reconciliation, and provider-verified profit.
- An independently monitored Windows service/Task Scheduler setup and
  restart behavior with owner approval, plus encrypted, verified off-device
  disaster recovery.
- Market pilot and meaningful owner KPIs for the learning/strategy loop.

None of these are silently marked DONE by unit tests or adding a pause
button. More workers, frameworks and tool connectors are not a substitute
for verified business outcomes.
