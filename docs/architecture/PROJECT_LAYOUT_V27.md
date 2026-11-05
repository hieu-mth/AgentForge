# AgentForge target layout — incremental migration, not a destructive move

\`\`\`text
AgentForge/
├── ai/                    AI domain documentation, role/workflow specs
├── ui/
│   └── dashboard/         React + Ant Design standalone frontend source
│       ├── src/
│       ├── package.json
│       └── dist/          generated build, gitignored
├── src/
│   └── agentforge/        stable Python backend/API/execution package
│       ├── ai/            future AI subpackages (migrate gradually)
│       └── control_center_static/  legacy UI fallback
├── skills/                existing trusted executor contracts
├── workspace/             user-owned products/media/proposals (gitignored)
├── data/                  SQLite/audit/approvals/policies (gitignored)
├── tests/                 Python/Node regressions
├── scripts/               maintenance and safe cleanup
└── docs/                  architecture, milestones, runbooks
\`\`\`

## Hard file rules

1. \`ui/\` is source code. **Never** store output websites, MP4s or production leads in UI.
2. \`workspace/\` is generated **products**. Do not include source code or build assets of
   the control panel here. Never delete it as a cache.
3. \`data/\` is SQLite, job history, approvals and local policy. Never delete or
   reset it just to resolve a frontend regression.
4. \`ai/\` holds domain ownership and future stable manifests. Python module
   locations stay under \`src/agentforge/\`; moving them wholesale would
   break imports, CLI entrypoints, stored skill IDs and user machine upgrades.
5. \`ui/dashboard/dist/\` and \`ui/dashboard/node_modules/\` are disposable
   generated dependencies/build artifacts. Rebuild, don't commit.
6. New optional frontend always uses the **same authenticated local backend**
   and CSRF/SHA review gates; the frontend is not the permission system.

## Interface boundary

React \`/dashboard/\` → same-origin \`/api/*\` → Python Control Center →
model/skill planner → SQLite/data, local workspace artifacts.

The React build is served by Python (no CORS, no duplicated Owner tokens,
no second public service). During local frontend development Vite can proxy
\`/api/*\` to Python on port 8780, keeping a same-origin browser API.

## Current first slice

Implemented in React: Owner login, prompt-first planning, SHA owner goal
approval and gated run/resume, task read-only details, website desktop/mobile
preview, owner feedback and apply, overview, read-only Finance/Team/Channels/
Settings. The legacy dashboard remains the fallback for image studio,
schedules, growth CRUD and operations until migrated in focused PRs.

## Safe upgrade and cleanup

- Run \`git status --short\` before pull.
- Do not move/rename \`data/\` or \`workspace/\`.
- Build React from \`ui/dashboard/\` with \`npm install\` and \`npm run build\`.
- Safe Python cache inventory remains \`scripts/repo_hygiene.py report\`;
  that script never deletes business assets.
- A future storage retention pipeline needs backup, digest verification,
  owner approval and explicit record IDs before any deletion.
