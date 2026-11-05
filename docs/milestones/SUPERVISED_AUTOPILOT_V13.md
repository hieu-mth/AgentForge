# AgentForge V1.3 — Supervised Autopilot

This pilot delegates **proposal-only** AI drafts in a local SQLite queue. It does not autonomously publish, deploy, spend, access customer accounts or execute browser/shell/network search. Existing S1/S4 owner approval, S5 manual handoff and emergency Pause remain.

## Eligible work

- media.copy_draft: produce an original storyboard draft for owner review.
- web.create: produce source proposal; applying the source still requires authenticated inspection and explicit SHA approval.

Each trusted skill is allowed only when it declares exactly one estimated model call and only model.invoke plus workspace.propose permissions. Unknown/new contracts are rejected. Pending queue maximum: 25.

**Budget warning:** UTC daily cap reserves estimated model invocations, NOT provider-enforced currency or token cost. Underlying providers may bill tokens and may internally retry. Do not enter PII, passwords or sensitive customer prompts into the unencrypted local database. External model usage can incur costs.

## Windows owner setup after merge

Run these commands from D:\AgentForge in PowerShell:

    git pull --ff-only origin main
    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 report
    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 configure --daily-model-calls 2 --enable --confirm-delegation

The initial state is DISABLED. Configure is an **explicit standing owner approval** for only the two built-in proposal skills above. The model provider must be configured separately using existing AgentForge setup.

Create a local JSON request file (e.g. draft-request.json) with non-sensitive content:

    {"topic":"Tư vấn chọn nệm","audience":"Người mua nệm","goal":"Đề xuất storyboard để chủ sở hữu duyệt"}

Enqueue WITHOUT calling any model:

    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 submit media.copy_draft --input-file .\draft-request.json

Dispatch one queued job only with explicit command-level permission:

    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 once --allow-model

Or run a foreground queue processor (Ctrl+C to stop):

    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 run --allow-model --interval 60

For a website source draft, use skill web.create and a JSON input containing slug (new slug, 3-40 lowercase letters/digits/hyphens) and brief (20–600 characters). Generated source must still be reviewed and SHA-approved through the existing owner workflow, never auto-applied.

## Owner-approved recurring AI draft schedule

To create a repeating draft **intake** (not publishing or deployment), reuse the
same JSON request file and specify the first future time in ISO-8601 with an
explicit time zone. For example, a future UTC time in PowerShell:

    $firstDue = (Get-Date).ToUniversalTime().AddHours(1).ToString("yyyy-MM-ddTHH:mm:ss+00:00")
    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 schedule media.copy_draft --input-file .\draft-request.json --first-due $firstDue --every-minutes 1440 --confirm-schedule

A running V1.3 queue processor picks up at most one due schedule intake per
poll, then dispatches at most one reserved model job. Missed intervals are
skipped rather than replayed on resume, and quota remains the shared UTC
daily ceiling. Disabled delegation prevents new due work from being enqueued;
global owner Pause blocks this intake as well. The schedule metadata appears
in the redacted report. Recurring input is the exact owner-supplied payload,
not a self-modifying AI-generated objective.

## Review, emergency stop, recovery

    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 report
    .\.venv\Scripts\python.exe -m agentforge.task_history list
    .\.venv\Scripts\python.exe -m agentforge.ops_control pause --confirm-pause

To revoke future model dispatch:

    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 configure --daily-model-calls 0 --confirm-delegation

The report provides only job ID, skill, status, task ID and reserved quota, without prompt/model output. Read outputs in existing owner Task History. An ambiguous DISPATCHING job consumes its reserved quota and is NEVER automatically replayed, even after restarting. Manually inspect provider/builder outputs before deciding to create a new job.

Global owner Pause blocks new dispatch, but not an already-running network call. A disabled autopilot policy does not delete tasks or queued jobs.

## Boundaries and acceptance

- SQLite BEGIN IMMEDIATE atomically reserves quota before each S1 invocation, across concurrent workers.
- A job's estimated quota is consumed on failure/interrupt; retries require a new owner request.
- Model outputs are unverified proposals only, not facts, commercial claims, applied website files or public posts.
- This V1.3 accepts owner-submitted jobs and explicitly approved recurring draft intake; it does **not** independently invent strategy or expand skill permissions.
- No always-on Windows service is installed. The local processor runs only while started and the PC is awake.
- Run tests on Windows:

    .\.venv\Scripts\python.exe -m unittest discover -s tests -q
    node --test tests/test_control_center_task_detail.cjs tests/test_control_center_v11.cjs tests/test_ops_control_ui.cjs

Tests mock paid model dispatch and cannot establish live provider/billing readiness.
