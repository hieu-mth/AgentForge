# Company Operations V1.1 — owner-operated local business cockpit

**Commit scope:** usable Goal input validation, task reports and safe errors.
**Not equivalent:** official YouTube/TikTok posting, ad buying, financial
verification, 24/7 service, customer CRM or autonomous business growth.

## What changed

- Control Center Goals form lists existing S3 dataset IDs from the existing
  authenticated bootstrap payload; no fabricated \`demo-example\` default.
  A preflight check can be explicitly requested before creating a Goal.
- The server **independently** checks local dataset/campaign references at
  Goal propose, SHA approve, and run/resume. Browser validation is UX; server
  validation is the authority. A missing reference blocks the operation
  before creating a Goal or running any new child task.
- An authenticated, CSRF-protected \`POST /api/goals/preflight\` is
  read-only, requires \`{"ack":"PREFLIGHT","template":"campaign.review",
  "inputs":{"dataset":"demo-..."}}\`, and returns a stable safe code such as
  \`DATASET_NOT_FOUND\` or \`CAMPAIGN_NOT_FOUND\`.
- Goal steps that have produced a child task now contain a
  **Xem kết quả / lỗi** button. It opens the existing accessible Task
  Details modal from Goals as well as Task History.
- The modal displays an *allowlisted* analytics/growth report projection:
  metrics, by-channel numbers, investigative signals, warnings, synthetic
  designation, and imported source count. No raw requests, customer rows,
  source filenames/paths, tokens, prompts, or arbitrary model text leave
  the backend. Independent financial verification remains **false**.
- Known S3 dataset exceptions receive stable non-sensitive error codes.
  Unknown exception messages remain deliberately redacted.
- Unchanged: fixed trusted S4 plan templates, immutable approval SHA,
  granular tool permissions, local owner authentication, scheduler
  read-only limit, S5 manual upload only, and all prior SQLite schemas.

## Windows owner acceptance

In a PowerShell console, from \`D:\AgentForge\`:

\`\`\`powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
.\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Regression tests failed" }
.\.venv\Scripts\python.exe -m agentforge.ops_doctor
.\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780
\`\`\`

Log in using the locally printed one-time owner code. Open
\`http://127.0.0.1:8780\`, force refresh with Ctrl+Shift+R.
Do not paste your login code anywhere.

**Acceptance 1 — invalid dataset**: On Goals & Phê duyệt select
\`campaign.review\`. Change the JSON dataset to \`demo-example\`. Click
**Kiểm tra dữ liệu**. Expect \`DATASET_NOT_FOUND\`; clicking
**Tạo kế hoạch** must refuse without creating any Goal. Do not grant
extra tools or run anything.

**Acceptance 2 — known dataset**: Go to Intelligence, confirm one
actual \`demo-...\` ID. Return to Goals and select that ID from the
dataset picker (the JSON updates automatically), or use a genuine
owner-imported dataset. Validate. Propose → inspect SHA/inputs →
approve → run with zero extra grants (for \`campaign.review\`).
Expect four completed local read-only analytics steps when the
data are well-formed.

**Acceptance 3 — result viewer**: Click **Xem kết quả / lỗi** on
\`analytics.content_report\`, \`analytics.opportunity_score\` and
\`analytics.finance_report\` in the successful Goal. Confirm content,
metrics, warnings, and DEMO flags appear in the modal. It must not
claim real net profit, platform verification or automatic publication.

**Acceptance 4 — campaign reference**: \`growth.review\` requires a
real S5 campaign ID. Missing campaigns are blocked before approval.
Existing manual evidence records/approved tasks are never overwritten.

## What to test before calling this a real AI company

1. An owner-approved public website with accurate product and contact data
   (not demo phone, invented price, warranties or affiliate claims).
2. Consent-aware, privacy-preserving lead capture outside the current local
   no-PII ledger, plus a real follow-up and affiliate attribution process.
3. One legitimate owner-controlled publishing channel with a separate
   restricted OAuth token, preview, idempotency, receipt and revocation.
4. Real budget and provider usage/cost observation; verified financial
   settlement with taxes, refunds and all costs separated from owner notes.
5. Manual kill/stop and recovery rehearsal on the actual Windows machine;
   encrypted off-device backups and documented cutover.
6. A 14-day pilot comparing decisions based on real funnel results, not a
   suite of synthetic PASS statuses.

No real customers, account grants, verified bank amounts or unattended
publication are present in this repository. Those **require** owner inputs
and acceptance and cannot be completed from Git permission alone.
