# AgentForge

**Local-first, human-controlled AI business research and product prototyping.** AgentForge is a Python 3.13 prototype built with LangGraph and SQLite. It can research opportunities, manage owner-reviewed market/customer evidence, and propose small static web products. It is **not** an autonomous company, hardened sandbox, or production deployment system.

## Strategic direction and context

See **[AgentForge Master Project Context & Strategic Roadmap](docs/AGENTFORGE_MASTER_CONTEXT.md)** for the long-term Autonomous AI Company vision, skill-first roadmap (S1–S5), delegated autonomy principles, and the C8F technical snapshot. The master context describes **future goals separately from implemented functionality**; this README and the source code document the current MVP.

## Capabilities

- **Model routing:** local Ollama (`local_primary`, `qwen3:8b`) or an opt-in Anthropic-compatible gateway (`cloud_primary`).
- **Opportunity research:** two focused searches, source leads, cautious reports and local checkpoints; search snippets are **not** verified facts.
- **Source/evidence review:** approved HTTPS page reads, quote matching, owner decisions, and separate vendor market-intelligence classifications.
- **Customer validation (C7A–C7C):** anonymous, consent-based interview intake; retain/follow-up/reject decisions; two owner-confirmed accounts can support only the `customer_problem` scope. Neither interviews nor advertised prices prove payments or demand on their own.
- **AI Product Builder (C8A, premium-first default):** one model call generates an offline, premium-styled `index.html` using the shared V2 design kit as a **proposal**. Only an owner-approved, digest-matched `apply` creates files in `workspace/products/<slug>/`. No automatic execution, browser automation or deployment.
- **Product revisions (C8B):** proposes changes to an existing `index.html`, shows a read-only diff, checks the original file fingerprint, and requires explicit digest-matched approval before replacing it. The prior version is backed up locally.
- **Static quality & preview (C8C):** read-only HTML/accessibility/responsive heuristics and an optional ignored-data preview of a pending revision. No browser is opened or code executed automatically.
- **Browser validation (C8D):** optional owner-started headless Chromium screenshots at mobile/tablet/desktop sizes; reports overflow, JavaScript errors, and blocked ordinary HTTP requests without changing the product.
- **Browser-guided fixes (C8E):** local-only triage of C8D reports, optional one-call AI fix proposals for verified issues, and the same owner-gated C8B approval path. Passing browser reports never trigger AI calls.
- **Bounded workflow (C8F):** immutable local checkpoints coordinate baseline browser test, optional one-model fix proposal, candidate browser test and separate C8B owner approval. A PASS report never triggers a model call.
- **Control Center V1 & local operations:** responsive authenticated localhost owner UI (default port 8780), SHA-reviewed S4 goal creation/approval/dispatch, one-run permission grants, sanitized tasks/S3/S5, read-only schedule management, local opt-in foreground scheduler with lock and heartbeat. New six-step growth.launch_local plan creates S2 video and two S5 manual-upload ZIPs; website.draft and a source-reviewed, SHA-gated apply flow create offline websites without repeating CLI commands. Default UI blocks model/network/browser/process tools until explicitly enabled; no public auth, real YouTube/TikTok API connection or bank verified revenue. See [Control Center V1 milestone](docs/milestones/CONTROL_CENTER_V1.md).
- **Revenue & Growth Operations (S5):** local campaign records, owner-approved S2 MP4/SRT manual-upload packages for YouTube/TikTok, consent-attested anonymous lead pipeline, immutable owner-reported commissions/costs with local booked-cost cap, S3 cross-ledger check, S4 read-only growth.review delegation, and a Dashboard growth table. **Not** authenticated channel creation/upload, bank reconciliation, verified profit or live provider budget enforcement. See [S5](docs/milestones/S5.md).
- **Company Brain & Delegation (S4):** bounded owner-governed goal templates, immutable SHA-reviewed plans, existing S1 skill/worker dispatch with per-step approval, durable step markers/no-replay recovery, local read-only scheduler, owner-owned memory and read-only Dashboard goal queue. NOT unrestricted AI planning, authenticated multi-user delegation, unattended 24/7 or hard money spending metering. See [S4 milestone](docs/milestones/S4.md).
- **Intelligence & Analytics (S3):** strict local CSV ingestion for daily performance and owner-recorded finance, source hashes/deduplication, content diagnostics, internal trend/opportunity hypotheses, descriptive A/B evaluation, pending-vs-confirmed cash, and read-only Dashboard overview. Seven S3 skills use existing S1 Task History and Policy Gate. No direct YouTube/TikTok/bank integrations, independently verified profit, or causal winner. See [S3](docs/milestones/S3.md).
- **Creative & Media Engine (S2):** local portrait PNG promo cards (Pillow), safe non-destructive edits, original WAV ambient, UTF-8 SRT captions, and owner-approved H.264/AAC MP4 via bundled FFmpeg; separately gated Windows/Piper offline TTS and optional one-model draft storyboard. Six reusable S2 skill contracts and real media QA integrated with S1 Task History. See [S2](docs/milestones/S2.md).
- **Web Design V2:** the same premium kit is now used at initial creation; its separate one-project-handle revision/preview/test/approve commands are for **existing** websites and owner-provided local photos. See [Web Design V2](docs/milestones/Web-Design-V2.md).

All generated text/code is untrusted. No workflow grants autonomous customer outreach, spending, publishing, package installation, or arbitrary shell execution.
Known C8C static FAIL findings (including `onclick` inline event handlers) now block new C8A proposals and both C8A/C8B applies. `PASS` means only these heuristics passed, not that the generated code or visual design is verified safe. Existing projects are not edited automatically; use reviewed revisions or local manual edits to repair a prior FAIL.


## Local setup — Windows PowerShell

Requires **Python 3.13+**.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

Default model: local Ollama (`qwen3:8b`), which must be installed and running. For an approved cloud gateway, set `AGENTFORGE_MODEL_REF=cloud_primary`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_AUTH_TOKEN` in the **gitignored** `.env`. Cloud requests may incur charges; never commit credentials.

Run the tests (no live model credentials or customer interviews required):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The repository's [GitHub Actions CI](.github/workflows/ci.yml) runs the same suite on Windows and Python 3.13 for pushes/PRs targeting `main`.

## V1.5 Offline Video Production & Owner Approval

Owner can edit a Vietnamese storyboard JSON locally and reuse existing
S1 media.compose, S2 FFmpeg render and media quality checks without another
AI model call. An optional immutable source-review SHA links back to the
previously rejected AI draft without automatically reusing its text. Video
production has a non-retryable render claim, digest-bound owner approval,
and a read-only review panel in the Control Center dashboard.
No auto-publish or platform integration is authorized.

Windows walkthrough: [Local Video Production V1.5](docs/milestones/LOCAL_VIDEO_V15.md).

## V1.4 Business Context + Content Quality Review

V1.4 adds owner-confirmed, SHA-digested business context for proposal-only
AI drafts, accent-sensitive deterministic Content Quality Gate and a local
human review ledger. Control Center Overview lists pending draft quality
reviews, while explicit owner CLI decisions remain bound to the immutable
output SHA. No auto-publishing, source apply, new model grants or additional
provider spend authority is added. Stale ambiguous briefs are quarantined
without reserving model quota.

Windows owner setup and limits:
[Business Context + Quality Review V1.4](docs/milestones/BUSINESS_QUALITY_V14.md).

## V1.3 Supervised Autopilot — bounded AI drafts

V1.3 introduces an opt-in, local SQLite AI draft queue with atomic daily
estimated-model-call reservations, owner-approved recurring draft schedules,
a metadata-only report and no auto-retry after uncertain dispatch. Only
`media.copy_draft` and `web.create` source proposals are delegated.
Browser, shell, posting, financial actions and applying website source still
require separate owner control.

The default is **DISABLED**. Daily model-call counts are **not** enforced
provider spend/token budgets. Windows setup, explicit enable/disable, review,
schedule commands and limitations: [Supervised Autopilot V1.3](docs/milestones/SUPERVISED_AUTOPILOT_V13.md).

## One-command Windows owner acceptance

From \`D:\AgentForge\` after \`git pull --ff-only origin main\`, launch
the read-only acceptance check (registry, owner pause state, SQLite,
datasets, scheduler and backup health) without any cloud/model use:

\`\`\`powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunTests
\`\`\`

Optional flags: \`-CreateBackup\` explicitly authorizes a local,
**unencrypted** verified backup, while \`-StartDashboard\` opens the
authenticated foreground Control Center. Neither option is enabled by
default; do not put private backup archives on GitHub or share the
one-time owner login code.

## Owner Operations V1.2 — pause/resume and attention inbox

A persistent local emergency pause can block **new S1 Skill, S4 Goal and
read-only Scheduler dispatch** until the owner explicitly resumes. It does
not forcibly terminate a model/browser/subprocess already in progress or
override a legacy command invoked directly outside S1. The Dashboard
Overview displays active/paused state and a focused owner attention inbox
for approval gates, failures, interruptions and stale scheduled work.

\`\`\`powershell
.\.venv\Scripts\python.exe -m agentforge.ops_control status
.\.venv\Scripts\python.exe -m agentforge.ops_control pause --confirm-pause
.\.venv\Scripts\python.exe -m agentforge.ops_control resume --confirm-resume
\`\`\`

See [Owner Operations V1.2](docs/milestones/OWNER_OPERATIONS_V12.md)
for exact safeguards, UI acceptance and recovery limitations.

## Control Center V1.1 — practical operations and readable results

Control Center V1.1 adds a source-backed S3 dataset picker, **Goal preflight**
and server-side dataset/campaign existence checks before planning,
SHA approval and execution. The owner can now open a completed Goal step
directly into the Task Details modal to read a **curated report** (aggregates,
channel signals, uncertainty and synthetic flags); raw prompts, file paths
and customer data are never serialized. Known dataset failures have stable
actionable error codes, with all other exceptions safely redacted.

Run the same local UI on \`http://127.0.0.1:8780/\`. Read
[Company Operations V1.1](docs/milestones/COMPANY_OPERATIONS_V11.md)
for exact Windows acceptance commands and a genuine 14-day pilot plan.
This is local business cockpit functionality, not authenticated external
publishing or verified net profit.

## Local Operations — backup, health and recovery staging

Existing Control Center V1 remains the owner-operated interface. Local
production-readiness tools add **consistent SQLite backup** (optional
website/video/channel artifacts), explicit checksum/SQLite verification
and a **non-destructive staged restore**; no active database overwrite.

```powershell
.\.venv\Scripts\python.exe -m agentforge.ops_doctor
$raw = .\.venv\Scripts\python.exe -m agentforge.ops_backup create --confirm-backup
if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
$backup = $raw | ConvertFrom-Json
.\.venv\Scripts\python.exe -m agentforge.ops_backup verify $backup.archive
```

Run `python -m agentforge.control_center_v1 --port 8780`, log in using
the locally printed one-time code (never share it), then go to
**Integrations → Local System Health**. This owner-authenticated view
displays SQLite integrity, backup inventory and scheduler status.
Backups in ignored `workspace/backups/` are **unencrypted** and are not
automatically uploaded, rotated, or restored.

See [Operations Readiness](docs/milestones/OPS_READINESS.md) for safe
staged restore and explicit limitations. No official YouTube/TikTok
publication, authenticated revenue reconciliation or public SaaS
hosting is implied.

## Control Center V1 — owner-operated local interface

After updating main and installing project extras, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780
```

Open http://127.0.0.1:8780/ and enter the one-time owner code printed
to the *local terminal*. Never commit, upload or share the code. The
old read-only Dashboard V0 remains available separately on port 8765.

Owner actions in V1 require an authenticated in-memory session,
same-origin JSON+CSRF, exact SHA approval, and per-run S1 grants.
External-capable tools are OFF by default. To explicitly opt in to a
bounded model/network/browser/FFmpeg workflow, restart V1 with
--allow-external-tools and still approve the grants per execution.
Never expose this single-user HTTP service outside localhost.

For opt-in recurring *read-only* goals on an always-on local machine,
use a separate terminal:

```powershell
.\.venv\Scripts\python.exe -m agentforge.ops_daemon run --confirm-unattended --interval 60
```

This is a foreground process, not a registered Windows service or
an automatic 24/7 cloud deployment. The scheduler never grants model,
posting or spending authority. See [Control Center V1 and acceptance
instructions](docs/milestones/CONTROL_CENTER_V1.md).

## S5 — Manual channel handoff & owner-recorded growth pilot

S5 completes the bounded S1–S5 local-first MVP series by joining
the existing S2 media video, S3 source-labeled analytics and S4 Company
Brain with lead/commission records and upload preparation. It does not
connect social or banking accounts; it **never** claims a handoff ZIP
was published on YouTube or TikTok.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m agentforge.skill_registry validate
$raw = .\.venv\Scripts\python.exe -m agentforge.growth_pipeline demo --confirm-local-media
if ($LASTEXITCODE -ne 0) { throw "S5 pilot failed" }
$s5 = $raw | ConvertFrom-Json
$s5.campaign
$s5.packages
$s5.reports.report
```

The isolated SYNTHETIC demo runs a local real FFmpeg video pipeline,
creates two ZIP packages, a dummy anonymous consent-attested lead and
pending commission, and completes a 3-step S4 read-only review. It never
makes a cloud call, uses real customer data, posts to a channel or
receives money. Actual publishing requires a licensed owner to upload
manually through an account they control. All financial statements
remain owner-recorded and verified net profit is null.

After restarting Dashboard V0, S5 campaign summaries appear with
clearly labeled SYNTHETIC DEMO data. Real owner-driven scenarios,
exact JSON input contracts and limitations:
[S5 technical milestone](docs/milestones/S5.md).

## S4 — Company Brain (bounded local-first pilot)

S4 coordinates the existing 18 S1–S3 skills into strictly bounded,
immutable, owner-approved plans. It does NOT grant new tool authority.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m agentforge.skill_registry validate
$raw = .\.venv\Scripts\python.exe -m agentforge.company_brain demo --confirm-demo
if ($LASTEXITCODE -ne 0) { throw "S4 demo failed" }
$s4 = $raw | ConvertFrom-Json
$s4
.\.venv\Scripts\python.exe -m agentforge.company_brain inspect $s4.goal_id
.\.venv\Scripts\python.exe -m agentforge.company_brain list
```

The explicit demo creates **only synthetic S3 metrics** then delegates
four real read-only analytics skills through S1 Task History. Goal plans
must be reviewed and approved with their SHA before separate execution;
model, browser and FFmpeg actions stop for explicit owner grants. The
local scheduler executes only owner-approved read-only templates when a
manual confirmed tick occurs. No auto retry after ambiguous crashes.

Restart Dashboard V0 to view S4 Goals and Schedules; all APIs remain
read-only and localhost-only. See [S4 usage and limitations](docs/milestones/S4.md).

## S3 — Offline Intelligence & Analytics acceptance

Source-aware S3 uses the Python standard library and SQLite (no cloud
analytics dependency). The first run generates ONLY synthetic data,
distinctly labeled from business results:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m agentforge.skill_registry validate
$raw = .\.venv\Scripts\python.exe -m agentforge.analytics_pipeline demo
if ($LASTEXITCODE -ne 0) { throw "S3 demo failed" }
$s3 = $raw | ConvertFrom-Json
$s3.dataset
$s3.reports.content.result.metrics
$s3.reports.finance.result
.\.venv\Scripts\python.exe -m agentforge.analytics_pipeline datasets
```

Expect demo-... dataset, two atomically audited CSV imports, six
deterministic reports and eight S1 task receipts. The new S3 Dataset view
in Dashboard V0 is read-only and labels synthetic data explicitly. Restart
the dashboard to load its updated code. For real files, use the strict
[CSV contracts and owner's import commands](docs/milestones/S3.md).

Confirmed cash is only owner-entered, **not bank-verified profit**. Never
treat example metrics, research hypotheses, A/B comparisons or a heuristic
opportunity score as authorization to spend or publish.

## S2 — One-command offline video acceptance

S2 is an **explicit opt-in** local media extra. Install dependencies only
when you choose to use it (Pillow and imageio-ffmpeg include a bundled local
FFmpeg binary; no cloud media API is involved):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
.\.venv\Scripts\python.exe -m pytest -q
$raw = .\.venv\Scripts\python.exe -m agentforge.media_pipeline demo nem-s2-pilot --render-video --confirm-media-run
if ($LASTEXITCODE -ne 0) { throw "S2 video render failed" }
$demo = $raw | ConvertFrom-Json
.\.venv\Scripts\python.exe -m agentforge.media_pipeline check $demo.assets.result.run_id
Invoke-Item $demo.video.result.video_path
```

Expect playable 9:16 MP4, captioned PNG frames, SRT sidecar and original
ambient WAV under ignored `workspace/media/<run_id>/`. The ambient sound is
**not speech**; Vietnamese offline TTS is optional and requires a separately
installed suitable voice/engine. Video generation runs an external local
binary **only** with the explicit media-run confirmation.

Owner-provided photos can be used after local rights attestation. No
automated social publication, cloud image generation, customer revenue
tracking, legal rights verification or model-generated claim approval.
See [S2 milestone and advanced commands](docs/milestones/S2.md).

## Usage

### S1 — Executable Skill Foundation (bounded local-first slice)

The [S1 foundation milestone](docs/milestones/S1.md) adds code-level
allowlisted skill adapters (five skills), explicit per-invocation owner
grants, SQLite Task History + events, a checkpointed web.audit workflow
and a read-only Dashboard V0 bound to 127.0.0.1. Unlike the declarative
registry, the separate skill_runner **can invoke existing modules**, but
will not invoke models, browsers, or network tools without explicit grants
and confirmations. No automatic product apply, publishing or spending.

Quick local smoke test after pulling the latest commit:

~~~powershell
.\.venv\Scripts\python.exe -m agentforge.skill_registry validate
.\.venv\Scripts\python.exe -m agentforge.skill_runner invoke web.quality_check --slug nem-tu-van
.\.venv\Scripts\python.exe -m agentforge.workflow_runner run nem-tu-van
.\.venv\Scripts\python.exe -m agentforge.task_history list
.\.venv\Scripts\python.exe -m agentforge.dashboard_v0 --port 8765
~~~

Open http://127.0.0.1:8765/ in a local browser while the dashboard is running.
The quick test reads your existing local website; it requires neither a
model call nor Playwright. Source changes after checkpoint block a deferred
browser check. Use task_history recover --confirm-recover to mark abandoned
running tasks interrupted (never re-execute them).

S1 is a bounded vertical slice, not a general planner, hardened sandbox,
authenticated cloud API or financial budget engine. Task inputs are stored
locally in an unencrypted SQLite file. Never store secrets in inputs, and
never expose the localhost dashboard remotely.

### S1.1 Skill Registry — discovery only

The new [S1.1 registry](docs/milestones/S1.1.md) lists five declarative contracts
for existing research and web capabilities. It validates skill metadata and
shallow input/output schemas without calling any model, network, browser or
product writer. **Skills are not yet invocable through this registry.**
Permissions and budgets are metadata only until a gated execution engine exists.

```powershell
.\.venv\Scripts\python.exe -m agentforge.skill_registry list
.\.venv\Scripts\python.exe -m agentforge.skill_registry inspect web.create
.\.venv\Scripts\python.exe -m agentforge.skill_registry validate
```

### Research

```powershell
.\.venv\Scripts\python.exe -m agentforge.research "Nhu cầu tự động hóa Excel cho shop online nhỏ tại Việt Nam"
```

Research outputs stay under `data/research/`.

### New website: premium-first creation — owner-gated

```powershell
# One model call, premium CSS and offline visuals added on this FIRST draft.
# Propose only; may incur cloud fees if cloud_primary is configured.
$draft = .\.venv\Scripts\python.exe -m agentforge.product_builder propose shop-landing "Tạo landing page tiếng Việt responsive, sang trọng cho dịch vụ tự động hóa Excel; không bịa giá hoặc thông tin liên hệ." | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Model proposal failed" }

# Inspect the source and SHA without manually copying an ID.
.\.venv\Scripts\python.exe -m agentforge.product_builder inspect $draft.proposal_id
notepad $draft.proposal_path

# Only after reviewing and accepting the exact source proposal:
.\.venv\Scripts\python.exe -m agentforge.product_builder apply $draft.proposal_id --confirm-write --sha256 $draft.sha256
```

Applying writes `workspace/products/shop-landing/index.html` with the premium presentation already included; **do not** run V2 just to improve the first draft. This command does **not** open, execute or deploy it. Review HTML/JS before opening it in a browser. The C8A creation flow never overwrites an existing project.

### Product revisions (C8B) — owner-gated

Use this only after a product already exists in `workspace/products/`. `propose` sends the current HTML to the configured model (and possibly a paid cloud gateway); it never edits the product. Review the proposed content and diff before approving the write.

```powershell
.\.venv\Scripts\python.exe -m agentforge.product_revision propose shop-landing "Cải thiện giao diện trên mobile, tăng khoảng trắng và làm rõ nút CTA."
$revisionId = "PASTE_REVISION_ID"
.\.venv\Scripts\python.exe -m agentforge.product_revision inspect $revisionId
.\.venv\Scripts\python.exe -m agentforge.product_revision diff $revisionId
notepad ".\data\company\product_builder\revisions\$revisionId.json"

# Only after reviewing the changes:
$revisionSha = "PASTE_SHA256_FROM_INSPECT"
.\.venv\Scripts\python.exe -m agentforge.product_revision apply $revisionId --confirm-write --sha256 $revisionSha
```

C8B backs up the prior `index.html` under `data/company/product_builder/backups/`, refuses stale proposals, and never launches a browser or deploys code. See [C8B](docs/milestones/C8B.md).

### Static quality checks and local revision preview (C8C)

```powershell
# Read-only inspection of an existing product.
.\.venv\Scripts\python.exe -m agentforge.product_quality check shop-landing

# For a pending, not-yet-applied revision:
$revisionId = "PASTE_REVISION_ID"
.\.venv\Scripts\python.exe -m agentforge.product_quality check-revision $revisionId
.\.venv\Scripts\python.exe -m agentforge.product_quality preview-revision $revisionId

# After reviewing the preview HTML source, YOU may open the preview_path
# shown above using Invoke-Item. The browser may execute untrusted JavaScript.
```

`preview-revision` writes only an ignored-data copy; it does **not** replace
`workspace/products/` or approve a revision. The checks are heuristics,
not browser tests or a security audit. If the revision is already applied,
use the `check` command on the current product instead. See [C8C](docs/milestones/C8C.md).

### Opt-in Chromium browser validation (C8D)

**Optional installation, with your approval** (not part of baseline dependencies). If your PC already has Edge or Chrome, you need only the Playwright Python package, not a separate Chromium download:

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
```

After reading the HTML, explicitly start browser validation:

```powershell
.\.venv\Scripts\python.exe -m agentforge.browser_validation project shop-landing --confirm-browser-run --browser-channel msedge

# For a pending, unapplied revision instead:
.\.venv\Scripts\python.exe -m agentforge.browser_validation revision PASTE_REVISION_ID --confirm-browser-run --browser-channel msedge
```

The `--browser-channel msedge` option uses Microsoft Edge already installed
on Windows; use `chrome` for installed Google Chrome instead. **You can skip
`playwright install chromium`** if the Playwright download times out and
your installed Edge/Chrome can launch. No browser download is initiated by
the validation command. The default without `--browser-channel` continues
to use downloaded Playwright Chromium.

C8D creates screenshots (`mobile.png`, `tablet.png`, `desktop.png`) and
`report.json` under ignored `data/company/product_builder/browser_checks/`.
It executes the HTML's JavaScript in a temporary browser context. HTTP routing
blocks ordinary off-document requests, but **this is not an OS/network security
sandbox**. No file is applied or deployed. See [C8D](docs/milestones/C8D.md).

### Browser-guided fix proposals (C8E)

For a completed C8D **project** run, inspect its findings first without a
model call or modifications:

```powershell
$runId = "PASTE_C8D_RUN_ID"
.\.venv\Scripts\python.exe -m agentforge.browser_fix plan $runId

# Only for FIX_PROPOSAL_AVAILABLE and if you approve a model call:
.\.venv\Scripts\python.exe -m agentforge.browser_fix propose $runId --confirm-model-call
```

The current `shop-landing` passed Edge and Chrome validation, so those
runs should report `NO_FIX_NEEDED` without a new AI request. For failures,
C8E converts only known browser issue codes and numeric data into a bounded
change request, then uses the existing C8B proposal flow. No automatic apply,
browser execution, retry or deployment. See [C8E](docs/milestones/C8E.md).

### Bounded Build → Test → Fix cycle (C8F)

C8F coordinates C8A/B/C/D/E and records **immutable local checkpoints**.
No autonomous browser execution, AI spending, retry, product write, or deploy.

For your already-PASS Microsoft Edge C8D report:

```powershell
# Reuse verified C8D output without rerunning Chromium or contacting an AI model.
.\.venv\Scripts\python.exe -m agentforge.product_cycle start shop-landing --report-run-id 2c6ef3dca9454cde92980d91ba518d8a

$cycleId = "PASTE_RETURNED_CYCLE_ID"
.\.venv\Scripts\python.exe -m agentforge.product_cycle inspect $cycleId
# Expected: NO_FIX_NEEDED
```

For future products, start a fresh cycle and explicitly authorize the baseline
browser run:

```powershell
.\.venv\Scripts\python.exe -m agentforge.product_cycle start shop-landing
$cycleId = "PASTE_RETURNED_CYCLE_ID"
.\.venv\Scripts\python.exe -m agentforge.product_cycle test $cycleId --confirm-browser-run --browser-channel msedge

# Only if C8D found recognized issues AND you authorize an AI request:
.\.venv\Scripts\python.exe -m agentforge.product_cycle propose $cycleId --confirm-model-call

# Only after a pending revision has been created, confirm its browser run:
.\.venv\Scripts\python.exe -m agentforge.product_cycle test-revision $cycleId --confirm-browser-run --browser-channel msedge
```

The final approval and file replacement **must** use the separate C8B
`product_revision apply --confirm-write --sha256 ...` command.
Each cycle allows at most one baseline browser, one model attempt and one
candidate browser attempt; a failed attempt is not retried automatically.
See [C8F](docs/milestones/C8F.md).

### Customer interviews

```powershell
.\.venv\Scripts\python.exe -m agentforge.customer_validation questions
.\.venv\Scripts\python.exe -m agentforge.customer_validation summary research-d3188c6a
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review summary research-d3188c6a
```

Only capture real, consented, anonymous interviews. Do **not** capture example or generated interview content as real evidence. See [C7A](docs/milestones/C7A.md), [C7B](docs/milestones/C7B.md), [C7C](docs/milestones/C7C.md), [C8A](docs/milestones/C8A.md), [C8B](docs/milestones/C8B.md), [C8C](docs/milestones/C8C.md), [C8D](docs/milestones/C8D.md), [C8E](docs/milestones/C8E.md), and [C8F](docs/milestones/C8F.md).

## Local data, security and status

- `data/`, `workspace/`, and `.env` are ignored by Git, **not encrypted**. Protect local disks and backups.
- SHA-256 checks detect later modifications; they are not evidence that an interview truly occurred or that generated code is safe.
- URL allowlists and path checks are **not** an OS sandbox. Run with minimum OS permissions and review source before execution.
- No real customer demand, willingness to pay, sales or revenue has been independently verified.
- Current operational milestone: **S1–S5 local MVP + Control Center V1.1**; remaining work is a real market pilot, external account authorization, provider-enforced spend limits, verified revenue and safe unattended operations. See `docs/milestones/COMPANY_OPERATIONS_V11.md`.
