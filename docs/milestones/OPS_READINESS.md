# Production-readiness increment — Local Backup, Recovery & Health

**Status:** additive owner-operations milestone following S1–S5 MVPs and
Control Center V1. Does not turn local-first AgentForge into a public
SaaS or a verified autonomous revenue-producing company.

The repository already contains Control Center V1 at
\`src/agentforge/control_center_v1.py\` with responsive static UI,
session authentication, SHA-reviewed goals, protected S1/S4 approvals,
local schedules, S5 handoff kits, and an opt-in foreground
\`ops_daemon\`. This increment **reuses those components** rather than
introducing a second dashboard, database schema or task executor.

## Capabilities

| Component | Actual behavior | Boundary |
|---|---|---|
| ops_backup create | SQLite online backup for all \`data/company/*.sqlite3\` databases; optional product/media/growth artifacts | No network, no cloud sync, no credentials collection |
| ops_backup verify | Per-file SHA-256, strict ZIP allowlist/manifest, SQLite integrity check, ZIP slip defense | Detects corruption but cannot certify external copies/retention |
| ops_backup stage-restore | Extracts a verified ZIP into a **new absent directory** | Never overwrites active databases; final cutover is manual |
| ops_doctor | Read-only integrity check, stale in-flight goals/tasks, skill registry, scheduler status, backup inventory | No automatic replay of interrupted tasks; no repair |
| Control Center V1 | Authenticated GET \`/api/ops/health\` + Integrations health panel | Owner session required, no POST to health API |

Backup archives contain **sensitive, unencrypted local content**.
Never upload or share them unprotected. No passwords, OAuth tokens,
customer personal details or network deployment are introduced here.
The tools are Python standard-library-only; no new runtime dependencies.

## One-pass Windows acceptance

From PowerShell in \`D:\\AgentForge\`:

\`\`\`powershell
cd D:\\AgentForge
git status --short
git pull --ff-only origin main
.\\.venv\\Scripts\\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
.\\.venv\\Scripts\\python.exe -m agentforge.ops_doctor
if ($LASTEXITCODE -ne 0) { throw "Database or registry integrity failed" }

# Explicitly approve a local backup of the project databases.
$raw = .\\.venv\\Scripts\\python.exe -m agentforge.ops_backup create --confirm-backup
if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
$backup = $raw | ConvertFrom-Json
$backup
.\\.venv\\Scripts\\python.exe -m agentforge.ops_backup verify $backup.archive
if ($LASTEXITCODE -ne 0) { throw "Backup verification failed" }

# Start authenticated Control Center V1; use its console-printed owner
# code locally. NEVER paste this code into GitHub, chats, logs or screenshots.
.\\.venv\\Scripts\\python.exe -m agentforge.control_center_v1 --port 8780
\`\`\`

Open \`http://127.0.0.1:8780/\` on the same machine, log in using the
temporary owner code, navigate to **Integrations → Local System Health**.
Expect SQLite integrity statuses and one local backup. The old V0
Dashboard still uses \`8765\` and remains untouched.

The health result can be \`REVIEW_REQUIRED\` for no prior backup,
in-flight tasks, or daemon errors; such warnings are intentionally
conservative. Failures from corrupted databases or invalid skill
registry return a nonzero CLI exit status. No remediation is performed
automatically.

## Optional coverage-aware first-party backup

The default backup remains database-only and is explicitly marked
`PARTIAL_DATABASE_ONLY`. For the known first-party persistence scopes (including
nested proposals, checkpoints, AI visuals, React apps, film jobs and receipts):

\`\`\`powershell
.\\.venv\\Scripts\\python.exe -m agentforge.ops_backup create --include-workspace --confirm-backup
\`\`\`

Full-mode scopes and safety exclusions are documented in
[`WAVE2_BACKUP_COVERAGE.md`](WAVE2_BACKUP_COVERAGE.md). A future unrecognized
storage root is marked `REVIEW_REQUIRED`, not automatically protected.
Legacy schema 1 archives are still readable but labeled `LEGACY_UNATTESTED`.
The original per-file 250 MiB and combined 1.5 GiB ceilings remain; oversized
assets need an additional Owner-managed encrypted archival process. No
cross-database atomicity or business-reference certification is claimed.

All generated backups are stored in the ignored
\`workspace/backups/agentforge-*.zip\` directory. They are NOT encrypted,
not synced, and not automatically rotated. Protect that directory with
Windows file-system permissions and an encrypted drive; copying to
independent storage and retention planning remain owner tasks.

## Inspect a backup; stage, don't overwrite

To verify or stage a previously created backup:

\`\`\`powershell
.\\.venv\\Scripts\\python.exe -m agentforge.ops_backup verify $backup.archive

$dest = "D:\\AgentForge-restore-review-$(Get-Date -Format yyyyMMdd-HHmmss)"
.\\.venv\\Scripts\\python.exe -m agentforge.ops_backup stage-restore $backup.archive $dest --confirm-restore
\`\`\`

The tool refuses any destination that already exists. It validates
every archive path, checksum, SQLite snapshot and file budget before
extracting. It cannot overwrite active local databases or execute
restored files.

**Manual cutover only:** stop Control Center, scheduler and any
AgentForge tasks; inspect all staged files, confirm business identity
and consent, and separately decide if/how to migrate. The tool does
not automate this because doing so without a coordinated transaction
could lose newer task, lead or financial events.

## Operations model

Control Center V1 is localhost-only with one owner code, in-memory
sessions, cookie, CSRF and origin guards. It is not hardened for
internet exposure or multi-tenant users. S4/S5 operational scopes
remain bounded: read-only schedules and explicit per-action approvals.
The scheduler must be **started by the owner**; the computer must stay on.

The remaining production integrations require their own independent
owner permissions and acceptance: YouTube/TikTok OAuth/API grants
(subject to platform restrictions), actual publish receipts and
idempotency, real provider-side budget enforcement, legitimate
financial/affiliate reconciliation, logging/monitoring, encrypted
data storage and identity/auth hardening. Those cannot be truthfully
claimed from a local synthetic demonstration.

Full architecture and prior delivery:
\`docs/AGENTFORGE_MASTER_CONTEXT.md\`,
\`docs/milestones/CONTROL_CENTER_V1.md\`,
\`docs/milestones/S1.md\`–\`S5.md\`.
