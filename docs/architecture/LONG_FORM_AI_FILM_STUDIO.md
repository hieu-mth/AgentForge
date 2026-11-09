# AgentForge — Long-form AI Film Studio (Phase 0: planner only)

## Verified scope

This module creates **immutable film plans with empty shot slots**, not moving videos. No inference, media runtime, subprocess, provider cost or YouTube upload occurs. Existing owner-gated static-frames-to-MP4 tools are unchanged.

A feature film can be divided into chapters, character reference descriptions and 4–15 second shot slots. A 2-hour example creates 900 shot slots at 8 seconds each. The plan intentionally says PLANNED_NOT_RENDERED, runtime_verified=false and youtube_uploaded=false. Do not treat this as a successful AI film generation.

## CLI (Windows PowerShell)

Build a demo plan on the local machine after installing AgentForge:

    cd D:\AgentForge
    .\.venv\Scripts\python.exe -m agentforge.domains.media.long_form plan --spec examples/film_studio/feature_fantasy.json --slug moonfire-pilot --output-root workspace/films
    .\.venv\Scripts\python.exe -m agentforge.domains.media.long_form inspect --slug moonfire-pilot --output-root workspace/films

The output is an exclusively written, SHA-validated film-plan.json in user workspace. Existing plans are not overwritten. The sample plot is original and high level; detailed scripts, scene timing and motion prompts are still missing.

## Next milestones (not implemented)

1. Original narrative screenplay and per-shot camera, action, dialogue, location, wardrobe, and character identity/voice references; versioned and reviewable.
2. Real image-to-video adapter (for example owner-approved local ComfyUI + Wan2.2 or appropriately licensed LTX-2.5). Select only after examining GPU/VRAM, licensing and successful actual motion proof. Support cloud only by explicit opt-in and cost cap.
3. Durable shot job ledger with workflow/model version, reference-image SHA, attempt IDs, video SHA, processing quotas, actual cost, failure and no-blind-retry recovery.
4. Audio production/dialogue timing, Foley, music rights, captions, mixing, chapter-level FFmpeg assembly and artifact QA; revise one bad shot without rerendering all.
5. QA gates on genuine motion, frame stability, shot-to-shot character identity, visual continuity, audio sync, duration, frame glitches, and review by the Owner.
6. Optional YouTube OAuth publisher, upload PRIVATE by explicit action, provenance, synthetic-content disclosure, no duplicate uploads and manual release approval; analytics only after authorization.
7. Benchmark first a 60–90-second motion pilot, then 5–10-minute sequence, 15–30-minute episode, then 1–3-hour film compilation. Don't scale until real quality/compute/cost/retention data supports it.

A 2-hour film at 8 seconds per shot represents 900 motion shots. Two attempts each means 1,800 generations. These are planning arithmetic, **not** predictions of GPU hours or price. Use genre/motion model providers as modular adapters, not hardcoded to one API.

## Guardrails

- Never describe this planning milestone as dynamic AI filmmaking.
- No AI source execution or public publishing without validated permission/isolation.
- Never clone the voice/likeness of a real person without appropriate consent.
- Use original screenplays, rights-cleared images, audio and music. YouTube disallows monetization of inauthentic, repetitive, mass-produced content; realistic synthetic content can require disclosure.
- Existing media, SQLite, owner data, proposal SHA, and the React dashboard are unchanged.
