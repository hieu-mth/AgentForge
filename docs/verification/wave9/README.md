# Wave 9 — Film Production: continuity and 60–90s pilot

**Status:** Code/Windows CI fixtures. Real ComfyUI GPU clips, assembled 60–90s movie, Owner visual/audio review: **PENDING**. This pipeline never auto-generates GPU footage, downloads models, clones voices or publishes.

## Contract

- Every shot references the exact Wave 8 film-plan SHA, job ID, clip SHA and technical receipt SHA. Rehash inputs before AND after FFmpeg. No arbitrary remote clips or repeated job IDs.
- Metadata from the original character bible: cast IDs, reference SHA, costume, location, props, action/camera and caption. Change in costume/location/reference requires Owner note; **not visual identity recognition**.
- 3–5 distinct 49-frame/12fps clips yield a ~12–20-second continuity preview. 15–22 distinct clips yield ~61–90 seconds (no artificial looping).
- Optional installed Windows SAPI/Piper TTS uses captions to create verified PCM WAV; otherwise output gets a silent AAC track. SRT is a UTF-8 sidecar, not burned-in.
- Owner-approved local FFmpeg assembles H.264/AAC MP4 with hard cuts, verifies frame count/duration/audio and full audio-video decode, saves SHA receipt. Technical PASS is not cinematic PASS.
- To change one shot, create a new episode version ID with source_episode_id and source_sha256; unchanged GPU clips are reused, but the new master video is encoded again.

## Step 1 — Plan locally before generating clips

~~~powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main

# Three-shot pilot
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.long_form plan --spec .\examples\film_studio\wave9_continuity_3shot.json --output-root .\workspace\films --slug fox-preview

# Separate 15-shot (~61s) pilot
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.long_form plan --spec .\examples\film_studio\wave9_film_60s.json --output-root .\workspace\films --slug fox-pilot
~~~

These commands create a SHA-bound film-plan.json once per slug. Use the [Wave 8 checklist](../wave8/README.md) to individually submit, reconcile, import and verify a real MP4 for EVERY shot in the same plan. Do not proceed until all source receipts exist.

## Step 2 — Auto-draft edit worksheet from actual receipts

~~~powershell
mkdir D:\FilmWorkflows

.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production draft --film-slug fox-preview --episode-id preview-v1 --shot-count 3 --output D:\FilmWorkflows\preview-edit.json
~~~

For 60s, use --film-slug fox-pilot --episode-id pilot-v1 --shot-count 15 --output D:\FilmWorkflows\pilot-edit.json, only after 15 real receipts.

The draft includes real job/clip/receipt SHA but Owner must fill ALL pending-owner-* tags and OWNER REVIEW REQUIRED: action/camera/caption fields. Keep visual bible, costume, reference, location and props consistent, or write a meaningful change_note. reference_sha256 may remain null when not available; never imply this is a validated identity pack.

~~~powershell
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production prepare --spec D:\FilmWorkflows\preview-edit.json
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production inspect --film-slug fox-preview --episode-id preview-v1
~~~

Save exact episode_sha256. Prepare does not call FFmpeg, model or GPU and refuses overwrite. For a new version, change episode_id, alter shot decisions and set source_episode_id plus prior source_sha256. No re-generation of unchanged source clips occurs.

## Step 3 — optional local TTS, FFmpeg assembly and SHA receipt

Trusted ffmpeg+ffprobe must be installed on PATH. Windows SAPI requires a local Vietnamese voice; Piper requires an installed binary and a voice model under models/voices with matching .onnx.json. Nothing is downloaded automatically.

~~~powershell
where.exe ffmpeg
where.exe ffprobe

# Optional TTS. Without this, video uses a silent AAC soundtrack.
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production voice --film-slug fox-preview --episode-id preview-v1 --episode-sha YOUR_EPISODE_SHA --engine windows --confirm-tts

# Or use --engine piper --voice-name your-voice.onnx
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production render --film-slug fox-preview --episode-id preview-v1 --episode-sha YOUR_EPISODE_SHA --confirm-ffmpeg
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production receipt --film-slug fox-preview --episode-id preview-v1
~~~

Files: workspace/films/fox-preview/productions/preview-v1/episode.mp4, captions.srt, render-receipt.json (and voiceover.wav if used). FFmpeg execution itself needs an explicit Owner action. Inspect output locally rather than auto-streaming/public upload.

## Dashboard

Start AgentForge with --allow-external-tools and log in as Owner. In AI Models & Routing → Film Studio Đợt 9, inspect episode ID/SHA/shot metadata, then choose voice or assemble. These actions require authenticated Owner session, CSRF, active Ops and an external-capable mode. No GPU generation or publishing is attached to the buttons.

## Owner acceptance

- Preview: actually watch 3–5 different motion clips; visually evaluate the recurring character, clothing, pose, camera and location.
- Production: provide 15–22 signed Wave 8 MP4 receipts, assemble a playable 60–90s video, verify subtitle timestamps and soundtrack/voice language, record encode duration and disk use.
- Reopen MP4, verify SHA receipt, and inspect full video/audio playback. Test one shot change via a new episode version, confirm other source clips are not regenerated.
- CI mocks do NOT establish real GPU throughput, film coherence, copyright/licensing, visual identity or production readiness.

Limits: hard cuts, metadata-only continuity, SRT sidecar, optional local TTS, no auto voice alignment, no long-form resume or YouTube OAuth.
