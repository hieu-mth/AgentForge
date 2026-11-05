# AgentForge V2.8 — Canonical repository structure

**Decision:** use a Python **src-layout monorepo** with one installable backend package,
one independently built React app, explicit AI/business domains, and completely
separate runtime databases and generated deliverables.

This is a *non-destructive* structural migration. There is no reason to reset
SQLite, copy \`workspace/\`, rewrite every legacy import or move the 24 skill
contracts simultaneously.

## Actual layout after V2.8

\`\`\`text
AgentForge/
├── ai/                                # AI domain specifications and architecture
│   └── README.md                      # Not a second Python executable package
├── ui/
│   └── dashboard/                     # React + Ant Design, Vite SPA
│       ├── src/{components,features}
│       ├── index.html
│       ├── package.json
│       └── dist/                      # Build output; NEVER commit
├── src/
│   └── agentforge/                    # Only installable Python package
│       ├── ai/                        # AI/model intake and adapters
│       │   ├── model_health.py
│       │   └── prompt_intake.py
│       ├── core/                      # Cross-domain bounded projections
│       │   └── result_view.py
│       ├── domains/
│       │   └── websites/
│       │       ├── feedback.py        # Owner revision planning
│       │       └── preview.py         # SHA-verified sandbox preview
│       ├── storage/
│       │   └── artifact_catalog.py    # Read-only artifact inventory
│       ├── architecture.py           # Machine-checked path/domain contract
│       ├── control_center_v1.py      # Existing API and session gateway
│       ├── brain_runner.py           # Existing core execution; later migration
│       ├── product_builder.py        # Existing business executor; later migration
│       ├── skill_runner.py           # Existing permission enforcement; later migration
│       ├── prompt_intake.py          # Thin legacy import shim
│       ├── result_view.py            # Thin legacy import shim
│       ├── website_feedback.py       # Thin legacy import shim
│       ├── website_preview.py        # Thin legacy import shim
│       └── artifact_catalog.py       # Thin legacy import shim
├── skills/                             # Trust-checked S1 skill TOML contracts
├── workers/                            # If present: worker/role config, leave intact
├── models/                             # Model metadata/weights; do not bulk-delete
├── tests/                              # Unit/integration/architecture contracts
├── scripts/                            # Windows maintenance & safe cleanup
├── docs/
│   ├── architecture/
│   └── milestones/
├── data/                               # Gitignored: SQLite, approvals, receipts
└── workspace/                          # Gitignored: produced sites/media/drafts
\`\`\`

The top-level \`ai/\` is for readable AI specifications and future role/workflow
definitions. *Executable Python AI code must live in \`src/agentforge/ai/\`*, because
\`agentforge\` is the package installed by pip. Creating another \`ai\` Python
package at repository root would cause ambiguous imports.

## Canonical module import map (actually migrated)

| Previous import (still works) | New canonical import |
| --- | --- |
| \`agentforge.model_health\` | \`agentforge.ai.model_health\` |
| \`agentforge.prompt_intake\` | \`agentforge.ai.prompt_intake\` |
| \`agentforge.result_view\` | \`agentforge.core.result_view\` |
| \`agentforge.website_feedback\` | \`agentforge.domains.websites.feedback\` |
| \`agentforge.website_preview\` | \`agentforge.domains.websites.preview\` |
| \`agentforge.artifact_catalog\` | \`agentforge.storage.artifact_catalog\` |

All six legacy module paths still import the **same callable object** from their
new home. Code is not duplicated. Existing API, tests and external CLIs may use
the old path during migration. **New code must import the canonical path.**

Other modules are not moved just to make the file tree look tidy. In particular
many of them calculate \`ROOT = Path(__file__).resolve().parents[2]\`: moving them
deeper changes their root directory, which could silently redirect database
and product output paths. Those modules require an explicit root abstraction,
tests, and compatibility migration first.

## Dependency direction

\`\`\`text
UI (ui/dashboard) ──same-origin HTTP──> API (control_center_v1)
                                         │
                                         ▼
                                 application/core orchestration
                                  ├─ AI adapters and policies
                                  ├─ domains (websites/media/growth)
                                  └─ storage (read-only inventory / SQLite access)
                                         │
                                         ▼
                              data/ and workspace/ on owner PC
\`\`\`

- UI never imports Python, opens SQLite, or spawns OS subprocesses.
- AI adapters may call supported local providers under existing permission gates.
- Core owns authorization, task state, model-call permissions and policy.
- Domains own product logic, review and output contracts.
- Storage owns safe paths and SQLite isolation; it must never auto-delete records.
- \`skills/\` is declarative and not executable code.
- \`ui/dashboard/dist/\` and \`node_modules/\` are rebuildable, not business data.
- \`workspace/\` holds **finished/generated user outputs**, never the React admin app.
- \`data/\` holds **persistent state**, not transient frontend files.

## Git and cleanup rules

Keep \`data/\`, \`workspace/\`, \`.env\`, \`.venv/\`, downloaded model weights,
\`ui/dashboard/dist/\` and \`node_modules/\` out of Git. Never purge \`data\` or
\`workspace\` in deployment or \`npm run build\`.

\`scripts/repo_hygiene.py report\` is safe/read-only. Its opt-in cleaning only
targets Python \`__pycache__/*.pyc\` within bounded source/test folders. Runtime
artifact deletion requires a separate verified backup + explicit owner review,
not a generic recursive cleanup command.

## Roadmap for remaining physical migration

Do the following in separate reviewed PRs, **not** as a blind rename:

1. Extract a shared repository-root/path module; verify all SQLite and output
   paths on Windows and test root consistency before moving modules with
   \`__file__.parents[N]\` dependencies.
2. Move \`model.py\`, \`model_registry.py\`, \`worker_registry.py\` gradually into
   \`agentforge.ai\`; keep stable wrappers and CLI contracts.
3. Move brain, approval and skill runners into \`agentforge.core\` only after
   compatibility coverage for Task History, permissions and paused schedules.
4. Move Product Builder, media and growth implementations into
   \`agentforge.domains\`; preserve proposal IDs, source SHA and SQLite schema.
5. Route the remaining legacy UI screens through React feature packages;
   remove \`control_center_static\` only after feature-parity, not prematurely.
6. Design a versioned backup/retention inventory to *safely* purge old runtime
   products when owner explicitly chooses them.

## Acceptance contract

\`tests/test_architecture_v28.py\` verifies canonical package directories,
callable compatibility, absence of file-relative root bugs in moved modules,
Git ignore rules and no direct SQLite/process access from the React frontend.
Windows CI runs that together with Python regressions, React build and
PowerShell acceptance. CI proves technical compatibility; business
deployment, image quality, authenticated YouTube/TikTok and real financial
profit remain unverified until externally tested.
