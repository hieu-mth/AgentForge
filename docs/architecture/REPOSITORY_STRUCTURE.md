# AgentForge — repository layout & file governance

## Source of truth

- `src/agentforge/`: trusted Python services, S1–S5 backends and CLI entrypoints. Do not move stable modules as part of visual redesign; preserve imports and existing SQLite schemas.
- `src/agentforge/prompt_intake.py`: small, deterministic mapping from plain-language owner prompts to fixed, owner-reviewed S4 plans. It is **not** an autonomous unconstrained agent.
- `src/agentforge/control_center_v1.py`: localhost HTTP transport, session/CSRF and allowlisted owner API actions (legacy filename retained for backwards compatibility).
- `src/agentforge/control_center_static/`: vanilla app HTML/CSS/JS, no CDN, no frontend build pipeline. The prompt-first view is the default; legacy specialist views remain for power users.
- `skills/`: declarative skill contracts. Do not grant permission through prompt text.
- `tests/`: Python and Node regressions; do not put production datasets here.
- `scripts/`: operational/acceptance utilities. Destructive operations must require explicit confirmation.
- `docs/milestones/`: historical release notes; `docs/architecture/` for current structure and policy.
- `examples/`: synthetic/demo templates, never real customer records.

## Local files (NEVER commit or delete automatically)

- `data/`: business SQLite ledgers, reviews, approvals, schedules and job receipts.
- `workspace/`: local websites, MP4, image assets, proposals and human edits.
- `models/voices/`: locally downloaded/licensed weights.
- `.env` / `.env.*`: secrets (except example), model endpoints and keys.
- `.venv/`: Python environment.

The repository's .gitignore already excludes these paths. Inspect `git status --short` and all target paths before cleaning. Never run recursive generic `Remove-Item` against `workspace` or `data`.

## Safe cleanup

Inventory **only disposable Python bytecode**:

    cd D:\AgentForge
    .\.venv\Scripts\python.exe scripts\repo_hygiene.py report

Clean only `*.pyc` under validated `src/**/__pycache__/` and `tests/**/__pycache__/`, with deliberate consent:

    .\.venv\Scripts\python.exe scripts\repo_hygiene.py clean-cache --confirm-cache-clean

This is cache cleanup, not database vacuum, media cleanup, or project removal. It rejects symlink/junction traversal, never purges source, proposals, MP4, .env, SQLite, customer information, audit history, or outputs.

If retention becomes necessary, design a separate *owner-reviewed inventory → backup → verify backup → explicit delete by IDs* flow with integrity checks and retention policies. Do not use file extension or age alone to delete business artifacts.

## UX / workflow contract

Prompt input → deterministic classification → immutable S4 plan → explicit owner SHA approval → existing S1 skill permission gates → task result → visual owner review → manual handoff. No prompt should silently execute model/network/process/publish actions. Currently only website/landing-page and storyboard intake routes are supported; other intents return a clarifying status instead of inventing a workflow.

For a landing page, a drafted HTML/SVG result is **not** equivalent to photorealistic AI image generation. Real photo-model integration is separate work, with explicit model permissions and attribution review.

## Prioritized future cleanup

1. Gradually split `control_center_static/app.js` into view-specific modules with a tested bundling-free loading mechanism; **do not rename wholesale without tests**.
2. Move HTTP route handlers toward a scoped API layer only after compatibility tests cover sessions, CSRF, errors and paths.
3. Add runtime artifact inventory + retention decisions only with a verified backup and owner approval.
4. Plan proper finance verification and channel OAuth adapters separately; do not conflate demo and production records.
