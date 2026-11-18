# Video-first consolidation: dependency decisions

Status: IN PROGRESS — this is a source-level inventory, not runtime certification.
Branch: `refactor/video-studio-focus`.

## Confirmed from source

- `agentforge/features/media/workflow.py` implements an older storyboard-to-MP4 lifecycle backed by `media_workflow_v15.sqlite3`; its `_business_check` requires an Owner business profile from `quality_v14`. This is unsuitable as the mandatory entry point for a general cat-video studio.
- `agentforge/features/film_studio/production.py` handles film production plans, voice and MP4 assembly, requires verified ComfyUI motion clips and explicit Owner confirmation. It explicitly does not certify artistic quality or character identity.
- `agentforge/api/routes/media.py` exposes film motion/render/voice actions and image generation, but is not yet a single coherent production API.
- `dashboard/src/features/MediaStudio.jsx` is currently a navigation page, not a renderer or production orchestration UI.
- The sidebar was reduced in PR #127; hiding navigation does **not** disable backend routes or remove their code.

## Target boundary (not yet implemented)

One video project lifecycle with script, source media, character references, shot assets, voice, motion, render, review and export. Use existing film motion/production and media asset components where possible. A video must not be called AI-motion-complete if it contains only static frames.

## Dependency-first cleanup sequence

1. Inventory all imports and API callers for `media.workflow`, `film_studio`, `media_assets`, `media_render`, image generation, and approval routes.
2. Select canonical project IDs, stage statuses, manifest and immutable artifact references. Define explicit migration/read-only handling for old production records.
3. Route the Dashboard and API through one orchestrator; retain existing security/Owner approvals.
4. Run focused unit and API regression tests, dashboard navigation tests/build, and FFmpeg technical QA.
5. Run local GPU/ComfyUI/TTS tests on the Owner machine and manually inspect video output before marking production ready.
6. Only then remove unused business/web modules, their routes, imports, tests and docs in dependency order.

## Safety constraints

- Do not delete Owner data, workspaces, generated media, models, SQLite DBs, or credentials.
- Do not remove old production readers until their persisted artifacts can still be accessed or exported.
- No automatic publishing or external execution without existing Owner consent.
- Do not merge this branch while regression tests and runtime acceptance are unverified.

## Known limits

No local runtime or CI test was executed during this connector-based change. Existing video quality and model readiness remain unverified.
