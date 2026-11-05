# AgentForge V3.3 — Architecture freeze for owner acceptance

## Final target tree (source of truth)

\`\`\`text
AgentForge/
├── ai/                        Human-readable role/workflow specifications
├── ui/
│   └── dashboard/             React + Ant Design source and Vite build
│       └── src/
│           ├── components/
│           └── features/
├── src/
│   └── agentforge/            The only installable Python runtime
│       ├── ai/                Model registry, worker registry, prompt intake
│       ├── core/              Planner, runner, task/skill state & permission gates
│       ├── domains/
│       │   ├── websites/      Builder, assets, revision, QA, image generation
│       │   ├── media/         Scenes, render, QA, workflow
│       │   └── growth/        Campaign ledger and reports
│       ├── storage/
│       │   ├── artifact_catalog.py
│       │   └── retention.py   SHA backup, reversible quarantine and restore
│       ├── paths.py           Canonical repository/runtime roots
│       ├── control_center_v1.py  Local authenticated API (filename retained)
│       └── *.py              Legacy aliases + remaining low-coupling modules
├── skills/                    Declarative trust-checked skill contracts
├── workers/                   Worker/role configuration
├── config/                    Model registry TOML (no secrets)
├── tests/                     Python/Node/architecture regressions
├── scripts/                   Owner maintenance and cache-only cleanup
├── docs/
│   ├── architecture/
│   └── milestones/
├── data/                      Gitignored SQLite, audit and verified backups
└── workspace/                 Gitignored AI-produced websites, video and media
\`\`\`

**Clean ownership is about boundaries, not the absence of compatibility
files.** The flat \`src/agentforge/*.py\` modules retained for external callers
are intentional and are not allowed to introduce a second source of truth.
The executable implementations moved by V2.9–V3.1 live in the canonical
namespaces. The import alias tests verify they are the same Python objects.

## Milestones delivered

- **V2.9** shared repository paths and AI model/worker registries.
- **V3.0** planner, runner, skill policy and durable task engine in Core.
- **V3.1** Website/Media/Growth domain implementations.
- **V3.2** native React owner work areas, projects, image preview, approvals,
  schedules, operations, intelligence, growth and local settings.
- **V3.3** bounded artifact inventory, SHA-verified backup, reversible
  quarantine and restore, with existing SQLite-safe \`ops_backup\` maintained.

## Invariants

1. Python remains \`src/agentforge\` (one package). React never opens SQLite
   or executes OS commands; it uses localhost owner API only.
2. The model backend and role policies live in AI; Core owns task authorization.
   Business domains own generated artifacts, not the React app.
3. \`data/\` and \`workspace/\` are persistent user data: never \`git clean -fdx\`,
   delete them as build output or move them as part of routine upgrades.
4. No automatic publication, autonomous spending, open browser permissions or
   unverified external financial integrations.
5. No silent retries after ambiguous model/GPU/process failures.
6. Human SHA approvals remain separate from model-call grants.
7. Backup verification and paused operations are prerequisites for quarantine.
8. V3.3 cleanup is **reversible quarantine, not permanent deletion**, and does
   not reclaim disk storage. Full SQLite disaster recovery uses
   \`agentforge.ops_backup\`.

## Owner acceptance checklist

On Windows PowerShell, with the existing server stopped:

    cd D:\AgentForge
    git status --short
    git switch main
    git pull --ff-only origin main

Rebuild UI if Node 22 is available:

    cd ui\dashboard
    npm install
    npm run build
    cd ..\..

Check system without modifying business data:

    .\.venv\Scripts\python.exe -m agentforge.company_v2 report
    .\.venv\Scripts\python.exe -m agentforge.storage.retention inventory

Launch authenticated React UI through Python:

    .\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780 --allow-external-tools

- React: http://127.0.0.1:8780/dashboard/
- Legacy diagnostic fallback: http://127.0.0.1:8780/

Owner should exercise **prompt → Goal → SHA approval → actual execution →
preview → feedback → product output**, then review AI image quality, task
recovery, schedule safety, review decisions, and backup/restore on a disposable
test website. Avoid testing quarantine on the real mattress-sales site first.

## Exit criteria and handoff

All PRs must pass Windows React build, Python regression and PowerShell
acceptance. Once V3.3 is merged, feature development **stops** until the
owner completes hands-on review. A green CI does not prove conversion,
YouTube/TikTok OAuth, public deployment, realistic model images, model billing,
or bank-verified profit. Discuss those only after actual pilot evidence.


## Final React retention integration

The retention backend is now available at
`/dashboard/ → Backups & Retention`, authenticated by the same session and
CSRF policy as all other owner actions. GET inspection/verification binds the
exact source/backup SHA to the current owner session before any mutation.
No SQL table or product directory is migrated during UI updates.

After this final PR merges, do not continue feature implementation until the
owner completes local review and decides how to prioritize actual product
quality, model capacity, channels and financial verification.
