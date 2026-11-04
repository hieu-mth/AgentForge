# Control Center V1 & Local Operations (post-S5)

S1–S5 delivered independently tested MVPs. This phase connects them into
one owner-operated local application without replacing the trusted S1
Permission Gate, S4 SHA-reviewed plans or S5 financial evidence boundaries.

## Delivered capabilities

| Feature | Implemented | What is not claimed |
|---|---|---|
| Control Center V1 | New full-width, mobile-friendly UI at localhost:8780 | Not an internet-facing SaaS |
| Authentication | Fresh console-printed owner code, in-memory 8-hour session | No multi-user identity provider |
| HTTP security | HttpOnly SameSite cookie, Host/Origin check, CSRF, strict CSP, bounded JSON, no CORS | Local HTTP is not safe over public networks |
| Goals | Propose, inspect SHA, approve, run/resume S4 templates from browser | No unchecked arbitrary tool execution |
| Permissions | One-run grants; external tools disabled by default, extra acknowledgement if enabled | No persistent blanket cloud/process grants |
| Tasks | S1 task history, artifacts (basenames) and status events | Private prompts/artifact bodies excluded from lists |
| Business | S3 datasets and S5 campaigns, owner-created campaigns and events | No verified revenue/real platform connectors |
| Scheduler | Create/toggle read-only plans and manual tick | No daemon auto-installed |
| Foreground worker | Opt-in polling, exclusive OS lock, heartbeat | Machine must remain powered on |
| Local channel launch | Six-step S4 S2→S5 workflow creating real MP4 and two manual-upload ZIPs | No YouTube/TikTok upload via API |

Existing V0 Dashboard and S1–S5 CLI/database files are unchanged.
The Skill Registry stays at 24 skills; this phase composes existing
skills rather than creating arbitrary additional execution adapters.

## One-pass Windows installation and smoke test

From PowerShell in D:\AgentForge after the new main commit:

    cd D:\AgentForge
    git status --short
    git pull --ff-only origin main
    .\.venv\Scripts\python.exe -m pip install -e ".[media]"
    if ($LASTEXITCODE -ne 0) { throw "Installation failed" }
    .\.venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    .\.venv\Scripts\python.exe -m agentforge.skill_registry validate
    if ($LASTEXITCODE -ne 0) { throw "Registry invalid" }
    .\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780

The terminal prints a fresh **ONE-TIME OWNER CODE**. Never paste it into
chat, GitHub, logs or screenshots. Open http://127.0.0.1:8780/ on that
computer and enter the code. The new Dashboard V1 starts without
external tool permission. The previous V0 remains on port 8765 if run.

### Safe Goal acceptance

1. On Growth & Revenue choose an existing demo-nem-... S5 campaign.
   If none exists, create a 0-VND local pilot campaign with the built-in
   JSON form. This creates a bookkeeping record only.
2. Under Goals & Phê duyệt choose the growth.review template, supply
   a matching input like {"campaign":"demo-nem-EXISTING"}.
3. Create a plan. Inspect its SHA and three read-only skill steps.
4. Approve that exact SHA, then explicitly press Run. Expect SUCCEEDED
   with 3 delegated tasks plus a parent task in Task History.
5. Log out and verify that the API requires a new login. Refresh the
   page before logout to verify the same session can restore its CSRF.

The plan SHA approval never automatically runs skills. Per-run grants
remain separate. Model/network/browser/FFmpeg actions are disabled in
the default V1 startup mode.

### Website Builder via V1 — no copy/paste of proposal IDs

Choose Websites -> Tạo website draft. The browser navigates to Goals
with the trusted website.draft template. Supply a NEW project slug and
a Vietnamese brief of 20–600 characters; set max_model_calls=1.
To run this plan, restart the server with --allow-external-tools,
review the plan SHA and explicitly grant model.invoke plus
workspace.propose and the confirm_model_call checkbox.

This skill proposes source only; it does NOT create website files. Go
to Task History, open the completed web.create task, then use Websites
-> Kiểm tra source to view the complete raw HTML displayed as ESCAPED
plain text. The authenticated server records that this exact proposal
SHA was inspected in this session. Apply only if you review the source,
claims, accessibility and layout. Confirm the displayed SHA explicitly
with the separate apply action. The S1 Product Builder validates source
and writes exclusively into workspace/products/<slug>/ without
overwriting existing products, executing HTML or deploying it.

The browser cannot apply a proposal without prior authenticated review
in the same session; the existing S1 digest and file/path checks remain
the final authority. A code-level quality check is NOT a human review of
commercial claims, images or business conversion quality.

### Local scheduler / daemon

One-off tick:

    .\.venv\Scripts\python.exe -m agentforge.ops_daemon once --confirm-tick
    .\.venv\Scripts\python.exe -m agentforge.ops_daemon status

To operate approved READ-ONLY schedules on a machine kept on, open a
separate PowerShell window and run (Ctrl+C to stop):

    .\.venv\Scripts\python.exe -m agentforge.ops_daemon run --confirm-unattended --interval 60

The process is foreground and does NOT self-install as a Windows service,
auto-start on reboot, or run while the machine is off. An OS file lock
blocks competing loops. Due schedule slots are durably claimed BEFORE
execution; missed intervals are skipped and uncertain operations are
not replayed after a crash. Heartbeat freshness is informative, NOT
cryptographic proof that a process is healthy.

### Local video + two channel handoff kits

The new S4 template growth.launch_local coordinates SIX steps:

1. media.compose — storyboard to original PNG/WAV/SRT.
2. media.quality_check — asset QA.
3. media.video_render — real FFmpeg MP4, requires external-process approval.
4. growth.bundle_prepare — verified offline YouTube ZIP.
5. growth.bundle_prepare — verified offline TikTok ZIP.
6. growth.quality_check — local bundle QA.

Prepare a valid S5 campaign first. In the Goal form choose
growth.launch_local, max_external_runs=1 and inputs similar to:

    {
      "campaign": "nem-pilot",
      "slug": "nem-pilot",
      "title": "Tư vấn chọn nệm",
      "description": "Cân nhắc nhu cầu trước khi chọn nệm.",
      "rights_attested": true,
      "scenes": [
        {
          "headline": "Bắt đầu từ nhu cầu",
          "caption": "Xác định kích thước và nhu cầu sử dụng.",
          "duration_seconds": 3
        },
        {
          "headline": "Tư vấn trước khi mua",
          "caption": "Trao đổi về độ nâng đỡ phù hợp.",
          "duration_seconds": 3
        }
      ]
    }

Rights attestation must be genuine; do not affirm ownership of
unlicensed audio, visuals or customer photos.

To allow the locally executed FFmpeg workflow, restart V1 explicitly:

    .\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780 --allow-external-tools

After exact SHA approval, grant workspace.write to run the safe first
steps. When execution reaches WAITING_APPROVAL for process.run, resume
with an explicit process.run grant and confirm_external_run checkbox.
The server requires a second external tool acknowledgement, and S1
still checks permission at each step. These local ZIPs DO NOT create
or publish actual YouTube/TikTok posts. Upload remains manual.

## Owner API contract

Authenticated GET: /api/bootstrap, /api/session, /api/goals/{id},
/api/tasks/{id}, /api/growth/{campaign}, /api/memory.

Authenticated JSON POST: /api/goals/propose,
/api/goals/{id}/approve, /api/goals/{id}/run, /api/goals/{id}/resume,
/api/schedules/create, /api/schedules/tick,
/api/schedules/{id}/status, /api/campaigns/create,
/api/campaigns/event, /api/memory/set, /api/logout.

All mutations require: localhost Host+Origin check, logged-in
HttpOnly session, matching CSRF header, strict request-size/schema
validation, an explicit action acknowledgment and the underlying
owner-gated policy. No HTTP route runs arbitrary Python, shell scripts,
SQL, browser navigation or platform publishing.

No internet binding, no CORS, no auto external tool approval. The
one-time owner code lives in process RAM only and is not written to
disk. Losing the terminal requires restarting the V1 server.

## What remains outside this delivered scope

- No YouTube/TikTok official API account creation, OAuth, autonomous
  publishing or platform analytics polling. Channel readiness remains
  MANUAL_HANDOFF_ONLY, pending owner-held developer app permissions.
- No real authenticated bank/affiliate feeds, verified payouts, tax/
  refund completeness or provider-side enforceable spending budgets.
- No built-in Windows service installer, always-on remote hosting,
  OS-hardening, high availability or backup/restore certification.
- No unrestricted AI CEO, unlimited recursive worker creation or
  fully independent market strategy without human control.
- Local SQLite stores are not encrypted; do not store customer contact
  data, secrets or access tokens. Authentication is single-owner and
  localhost-only, NOT a hardened public multi-user service.

Next real-business integration: run one owner-controlled mattress
campaign; obtain verified channel account permissions and official
OAuth grants; then build consented connectors, publish receipts,
idempotency and platform-side spend limits. Do not treat the offline
demo as evidence of marketing effectiveness or paid commissions.
