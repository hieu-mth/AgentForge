# Wave 10 — Publishing & Business Operations

**Status:** local release ledger, explicit Owner review, optional private-only YouTube OAuth CLI, signed video handoff, manual schedule intent and owner-recorded metrics **implemented in code/CI**. Real OAuth account, real private upload, platform analytics, public scheduling, ad spend, bank reconciliation and revenue **NOT VERIFIED**.

## Safety contract

- Use only Wave 9 `production.inspect_render` technical-pass `episode.mp4`, `captions.srt`, source episode SHA, render receipt SHA and MP4 SHA. The Owner must **watch the local MP4** and explicitly attest all content/music/voice rights; synthetic-media and kids declarations are Owner-provided booleans. Technical QA alone does **not** prove copyright, visual continuity or YouTube policy compliance.
- One immutable release per film episode, assigned UUID and SHA in local `data/company/film_publishing.sqlite3`. No script calls Google on prepare, inspect, attest or observe; the original MP4 is not copied or moved. Duplicate release attempts fail. File mutation invalidates release inspection.
- `planned_utc` is **only a local planning reminder**. Wave 10 has **NO automatic upload scheduler**, no YouTube `publishAt` call, no public/unlisted upload command, no advertising spend. Published/scheduled states in the local journal are Owner claims and not independent proof.
- Owner observation snapshots (views, likes, comments, watch minutes, UTC date) are **MANUAL** and have `platform_api_verified=false`. The existing Growth ledger continues to own VND spending/commission; no bank or provider reconciliation, YouTube monetization or automated finance claims.
- The optional `youtube_private` adapter opens the official desktop OAuth browser once for each explicit upload. OAuth client JSON **must be outside the repo**; access/refresh credentials are held in memory, not saved to AgentForge. It uses `youtube.upload` scope, `videos.insert` resumable upload with `privacyStatus=private` and the Owner disclosure fields. Checkpoint to `UPLOAD_ATTEMPT_UNCERTAIN` before the external insert. On an ambiguous network/API result **never automatically retry**: manually check YouTube Studio, then Owner can record the matching video ID. The API response is not evidence that a private video is approved for public viewing.

Official API references: [videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert), [video status/privacy and scheduling constraints](https://developers.google.com/youtube/data/reference/rest/v3/videos), [desktop OAuth flow](https://developers.google.com/youtube/reporting/guides/authorization/installed-apps).

## Windows — setup and local handoff

From the current repository, with no uncommitted local changes that need preservation:

~~~powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main

# Default safe features (OAuth dependencies are NOT installed unless selected)
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
~~~

Open `http://127.0.0.1:8780/dashboard/`, navigate to **Kênh xuất bản**. First generate real Wave 8 motion shots and complete Wave 9 assembled MP4. Then select the assembled episode: Dashboard reads exact source and render SHA. Enter YouTube title/description, rights and watched confirmation, synthetic/kids disclosures and optional future ISO8601 timestamp (planning only). Click **Chuẩn bị handoff local (Private)**; inspect the new SHA receipt and local MP4/SRT paths. Nothing leaves your computer.

For manual upload, open YouTube Studio yourself and choose `episode.mp4`, attach `captions.srt` if appropriate, review disclosures, and set `Private`. After checking Studio, enter its **11-character video ID** and Owner-observed privacy state in Dashboard; statistics may be entered as manual snapshots. Do not interpret Owner-reported public/scheduled as platform verified.

## Optional real YouTube private-only OAuth upload

**Only if you choose to enable networking and want a PRIVATE upload.** Configure a Google Cloud project, consent screen, enable YouTube Data API and create an **OAuth Desktop client**. Store the JSON outside the repo (for example `D:\OwnerSecrets\youtube-desktop.json`). The API and Google quota/account policies may vary. Never paste OAuth codes/tokens into Git, prompts or logs.

~~~powershell
cd D:\AgentForge

# Explicitly opt into cloud dependencies (default install does not do this).
.\.venv\Scripts\python.exe -m pip install -e ".[youtube]"

# Copy actual release_id + release_sha256 from Dashboard inspected release.
# Interactive browser consent opens locally, and only one private videos.insert
# is permitted after explicit confirmation.
.\.venv\Scripts\python.exe -m agentforge.integrations.youtube_private upload-private --release-id ACTUAL_RELEASE_ID --release-sha ACTUAL_RELEASE_SHA --oauth-client-file D:\OwnerSecrets\youtube-desktop.json --confirm-private-upload
~~~

The private upload command **does not change any public visibility or schedule**. Its result includes only the API-returned YouTube video ID, a private status and no credentials. If you receive `YOUTUBE_UPLOAD_UNCERTAIN`, look in YouTube Studio **before doing anything else**. Do not rerun the same command/release. Use the Dashboard manual attestation for a real ID you confirmed exists.

## Acceptance gates

CI runs full Python unittest, strict API Owner session/CSRF/sha gates, Dashboard build, OAuth client private payload contract, one-shot uncertainty, no local token persistence and ledger integrity tests, all with synthetic MP4 fixtures. **CI does not connect to YouTube or authorize a real Google account**.

Owner acceptance:
1. On Owner Windows PC, finish Wave 8 and Wave 9 **real video** acceptance, review source MP4/audio/rights.
2. Prepare a local release with real source and receipt SHA; inspect handoff and verify no outgoing calls.
3. Optionally connect OAuth Desktop in local browser; upload a **private** video, view it in Studio, verify exact video ID and privacy. Confirm a network interruption does not trigger auto-retry.
4. Manually record publication schedule/status if changed on YouTube Studio. Never mark scheduled as platform-controlled by AgentForge.
5. Add manual stats; reconcile finance through existing Growth records and bank/provider evidence externally. Do not infer earnings from views.

Wave 10 code PASS does **not** mark a channel connected, earn money or publish a video automatically.