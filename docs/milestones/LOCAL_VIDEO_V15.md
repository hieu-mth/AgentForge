# AgentForge V1.5 — Owner Storyboard Editing, Offline Video Production and Review

V1.5 reuses existing S1/S2 media skills. No new model call, browser, network access, platform publishing, bank/payment integration or unattended media subprocess is introduced. Content Quality V1.4 and V1.3 daily AI limits remain unchanged.

## Owner production workflow (Windows PowerShell 5.1)

Stop any old media-processing commands. Start at D:\AgentForge and use latest main after merge. Do not run the production command until you have inspected and edited the storyboard.

    cd D:\AgentForge
    git status --short
    git switch main
    git pull --ff-only origin main

Copy the bundled example to a local editable file (keep original as reference):

    Copy-Item .\examples\nem-ngu-storyboard-v15.json .\storyboard-v15.json
    notepad .\storyboard-v15.json

The JSON contains the existing S2 schema: slug (new safe slug 3-40 characters), title (<=88 chars), scenes (2–5 items), and for each scene headline (<=68 chars), caption (<=180 chars), duration_seconds (3–8). Total duration must be <=35 seconds. This is a **manually edited owner-supplied** artifact, not automatically accepted model output. If an S2 project already exists, choose another slug.

Prepare immutable local PNG frames, subtitles and ambient WAV, after checking the owner-edited text:

    .\.venv\Scripts\python.exe -m agentforge.media_workflow_v15 prepare --input-file .\storyboard-v15.json --confirm-edit --source-job-id 146da0dd1ccc46bbbf7675ceff7d4b22 --source-output-sha 6ef50746f8a4953ebdb7e39d0fd986dabd41b9c92be7328162dc9c919f392a1b

The source arguments reference an **existing owner-reviewed rejected AI draft** solely as provenance. They do not copy its content. The owner must edit and supply a new local JSON file. For a new standalone original storyboard, omit both --source-job-id and --source-output-sha.

The prepare output contains production_id, run_id and immutable storyboard_sha. Prepare reuses S1 media.compose with explicit local workspace.write. It does not run a model or FFmpeg. An uncertain PREPARING record must be investigated, never auto-replayed.

Review generated frames under workspace\media\RUN_ID and run read-only QA:

    .\.venv\Scripts\python.exe -m agentforge.media_pipeline check RUN_ID

After checking quality and consenting to an **installed local FFmpeg subprocess**:

    .\.venv\Scripts\python.exe -m agentforge.media_workflow_v15 render PRODUCTION_ID --confirm-local-process

This requires existing S1 workspace.write + process.run and input confirm_external_run gates. It runs FFmpeg locally with shell=False, verifies audio/video tracks and file digests. Rendering is **once-only**; a crash/uncertain subprocess leaves RENDERING for manual investigation and is not retried. The returned video_path points to workspace\media\RUN_ID\video.mp4.

Review the actual MP4 with a video player, listening for audio, checking Vietnamese text, health/marketing claims and customer contact information. Automatic structural VIDEO_PASS is not semantic verification. Do NOT approve based solely on quality status.

Check the redacted status in the Control Center Overview > Local Video Production or CLI:

    .\.venv\Scripts\python.exe -m agentforge.media_workflow_v15 report

When the video has been manually reviewed, use the actual video_sha returned by render:

    .\.venv\Scripts\python.exe -m agentforge.media_workflow_v15 decide PRODUCTION_ID APPROVE --video-sha VIDEO_SHA --confirm-review

Or REJECT. A review is immutable/once-only and bound to the verified MP4 content SHA. It does NOT upload, publish, enable a future automated action or grant external rights. The older S5 growth.bundle_prepare flow remains separately owner-gated, requires campaign, rights attestation and channel-specific manual upload.

## Security and operational boundaries

- V1.4 requires owner business context before creating media. Edited storyboard is checked for focus and prohibited phrases. PASS_HEURISTIC is not a legal/factual claim approval.
- Optional source provenance must match an existing V1.4 APPROVED or REJECTED media.copy_draft review with the exact SHA.
- Existing S1 adapter permissions and Owner PAUSED state are reused; no new model permission is granted. FFmpeg cannot execute without explicit process flag.
- Production decisions record only IDs, context SHA, storyboard SHA, run ID and video SHA; no customer PII or model prompts are stored.
- Video and local SQLite are **not encrypted**. Keep private source data out.
- No auto retries; no overwrite of existing video. Interrupted PREPARING or RENDERING entries need manual diagnosis.
- Owner APPROVE means “reviewed draft video,” not “legal clearance, commercial evidence or publishing consent.”
- No automatic platform upload, channel account login, conversion tracking or revenue verification.
- Windows CI tests use mocked model/render actions and cannot prove real FFmpeg, codec support or finished video quality on your machine. For actual video verification, run the owner process above with local FFmpeg and watch the MP4.

## Acceptance tests

    .\.venv\Scripts\python.exe -m unittest discover -s tests -q
    node --check src/agentforge/control_center_static/app.js
    node --test tests/test_control_center_task_detail.cjs tests/test_control_center_v11.cjs tests/test_ops_control_ui.cjs

Run a single owner-approved local video pilot before scheduling further automation.
