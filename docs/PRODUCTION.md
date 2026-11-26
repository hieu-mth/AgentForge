# Sản xuất, kiểm tra chất lượng và xuất bản

## Dựng thủ công từ motion receipts

This document covers the manual assembly workflow for existing motion receipts. For automatic storyboard-to-video drafts, use Studio video in the Dashboard. CI fixtures validate the contract; visual and audio quality require review of real output. Manual assembly does not dispatch GPU work, download models, clone voices or publish.

### Contract

- Every shot references the exact Motion film-plan SHA, job ID, clip SHA and technical receipt SHA. Rehash inputs before AND after FFmpeg. No arbitrary remote clips or repeated job IDs.
- Metadata from the original character bible: cast IDs, reference SHA, costume, location, props, action/camera and caption. Change in costume/location/reference requires Owner note; **not visual identity recognition**.
- Duration follows the verified source clips; the plan slots alone do not prove output duration. No artificial looping.
- Optional installed Windows SAPI/Piper TTS uses captions to create verified PCM WAV; otherwise output gets a silent AAC track. SRT is a UTF-8 sidecar, not burned-in.
- Owner-approved local FFmpeg assembles H.264/AAC MP4 with hard cuts, verifies frame count/duration/audio and full audio-video decode, saves SHA receipt. Technical PASS is not cinematic PASS.
- To change one shot, create a new episode version ID with source_episode_id and source_sha256; unchanged GPU clips are reused, but the new master video is encoded again.

### Step 1 — Plan locally before generating clips

~~~powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main

# Three-shot example
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.long_form plan --spec .\examples\film_studio\continuity_3shot.json --output-root .\workspace\films --slug fox-preview

# Separate 15-shot plan example
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.long_form plan --spec .\examples\film_studio\film_60s.json --output-root .\workspace\films --slug fox-production
~~~

These commands create a SHA-bound film-plan.json once per slug. Use the [Runtime và motion](RUNTIME.md) to individually submit, reconcile, import and verify a real MP4 for EVERY shot in the same plan. Do not proceed until all source receipts exist.

### Step 2 — Auto-draft edit worksheet from actual receipts

~~~powershell
mkdir D:\FilmWorkflows

.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production draft --film-slug fox-preview --episode-id preview-01 --shot-count 3 --output D:\FilmWorkflows\preview-edit.json
~~~

For the 15-shot example, use --film-slug fox-production --episode-id episode-01 --shot-count 15 --output D:\FilmWorkflows\episode-edit.json, only after 15 real receipts.

The draft includes real job/clip/receipt SHA but Owner must fill ALL pending-owner-* tags and OWNER REVIEW REQUIRED: action/camera/caption fields. Keep visual bible, costume, reference, location and props consistent, or write a meaningful change_note. reference_sha256 may remain null when not available; never imply this is a validated identity pack.

~~~powershell
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production prepare --spec D:\FilmWorkflows\preview-edit.json
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production inspect --film-slug fox-preview --episode-id preview-01
~~~

Save exact episode_sha256. Prepare does not call FFmpeg, model or GPU and refuses overwrite. For a new version, change episode_id, alter shot decisions and set source_episode_id plus prior source_sha256. No re-generation of unchanged source clips occurs.

### Step 3 — optional local TTS, FFmpeg assembly and SHA receipt

Trusted ffmpeg+ffprobe must be installed on PATH. Windows SAPI requires a local Vietnamese voice; Piper requires an installed binary and a voice model under models/voices with matching .onnx.json. Nothing is downloaded automatically.

~~~powershell
where.exe ffmpeg
where.exe ffprobe

# Optional TTS. Without this, video uses a silent AAC soundtrack.
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production voice --film-slug fox-preview --episode-id preview-01 --episode-sha YOUR_EPISODE_SHA --engine windows --confirm-tts

# Or use --engine piper --voice-name your-voice.onnx
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production render --film-slug fox-preview --episode-id preview-01 --episode-sha YOUR_EPISODE_SHA --confirm-ffmpeg
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.production receipt --film-slug fox-preview --episode-id preview-01
~~~

Files: workspace/films/fox-preview/productions/preview-01/episode.mp4, captions.srt, render-receipt.json (and voiceover.wav if used). FFmpeg execution itself needs an explicit Owner action. Inspect output locally rather than auto-streaming/public upload.

### Dashboard

Start AgentForge with --allow-external-tools and log in as Owner. In Studio video → Công cụ nâng cao, inspect episode ID/SHA/shot metadata, then choose voice or assemble. These actions require authenticated Owner session, CSRF, active Ops and an external-capable mode. No GPU generation or publishing is attached to the buttons.

### Owner acceptance

- Preview: actually watch 3–5 different motion clips; visually evaluate the recurring character, clothing, pose, camera and location.
- Production: provide verified Motion MP4 receipts, assemble a playable video, verify subtitle timestamps and soundtrack/voice language, record encode duration and disk use.
- Reopen MP4, verify SHA receipt, and inspect full video/audio playback. Test one shot change via a new episode version, confirm other source clips are not regenerated.
- CI mocks do NOT establish real GPU throughput, film coherence, copyright/licensing, visual identity or production readiness.

Limits: hard cuts, metadata-only continuity, SRT sidecar, optional local TTS, no auto voice alignment, no automated continuity certification in manual assembly.

## Tạo lại một cảnh trong Studio

Khi video đang chờ duyệt, mở storyboard và chọn cảnh cần tạo lại. Có thể yêu cầu tạo lại ảnh (và clip phụ thuộc nếu là phim chuyển động) hoặc chỉ tạo lại chuyển động từ ảnh đã lưu. Studio tạo phiên bản storyboard mới, giữ checkpoint các cảnh khác và yêu cầu Owner duyệt lại trước khi dispatch. Phiên bản cũ không bị ghi đè. AI viết lại prompt được cung cấp ngữ cảnh cảnh trước/sau nhưng không tự thay đổi chúng. Đây là sửa có giám sát, chưa phải QA thị giác tự động; Owner cần kiểm tra lại tính liên tục sau khi dựng.

## Liên tục chuyển động (pilot)

Trong Nội dung & phiên bản, chọn AI lập liên tục chuyển động. Model storyboard quyết định CUT, CAMERA_CHANGE hoặc CONTINUE và trạng thái đầu/cuối; Owner duyệt SHA mới. Với CONTINUE, adapter LTX đọc clip trước đã kiểm SHA, trích đúng frame cuối được dùng trong timeline (không phải frame cuối của clip thô), ghi nguồn frame và SHA vào motion ledger, gửi PNG đó thay cho ảnh FLUX dự kiến. CUT/CAMERA_CHANGE vẫn dùng ảnh riêng. Các cảnh tiếp nối phụ thuộc bị bỏ checkpoint khi nguồn thay đổi; cảnh độc lập được giữ. Không tự fallback khi frame nguồn thiếu hoặc không hợp lệ. CI kiểm tra trích frame bằng FFmpeg thật và logic dependency; hiệu quả hình ảnh và chuyển động trên LTX cần Owner nghiệm thu. Ảnh FLUX dự kiến vẫn được tạo cho tất cả cảnh trong pilot, kể cả cảnh tiếp nối.

## AI đánh giá frame mẫu (pilot có giám sát)

Tại Model AI, gán model hỗ trợ ảnh qua ChatGPT Plan, Ollama, OpenAI-compatible hoặc Anthropic-compatible tại tuyến Kiểm tra chất lượng hình ảnh (vision.qa). Metadata readiness chỉ kiểm tra endpoint, không chứng minh model thực sự hiểu hình ảnh. Bật quyền gọi tương ứng và FFmpeg. Trong storyboard của video đang chờ duyệt, chọn AI đánh giá cảnh; hộp xác nhận thông báo việc gửi ảnh ra cloud và khả năng tính phí. Pipeline kiểm tra SHA video và ảnh, lấy frame đầu/giữa/cuối cảnh và ranh giới trước đó, tạo contact sheet JPEG có giới hạn, gọi đúng model đã gán và lưu kết quả kèm SHA, revision, frame indices. Mỗi lượt cloud được tính vào ngân sách production; không tự fallback hoặc thử lại.

Kết quả PASS/FAIL/UNCERTAIN chỉ đánh giá các frame mẫu, không xác nhận toàn bộ chuyển động, âm thanh hoặc chất lượng điện ảnh. Chưa chạy QA tự động, chưa tự tạo lại và không thay thế Owner review. Cần benchmark model thị giác thực tế trước khi bật tự động.

## Kiểm tra chất lượng và so sánh video

On an executable rollback, leave drafts using the creative plan paused until the compatible build is restored. Older builds do not understand this layout or its approval digest. Registry rollback to the exact pinned profile remains supported by the existing dispatch guard.

Use separate draft, visual and motion ledgers and workspace paths for the baseline and candidate. Hold the script, enabled Model Hub assignments, workflow, encoder and rendering settings constant. Approve each storyboard through the existing Owner gate before media dispatch.

Run the resource sampler alongside each test draft. Use the approved test production ID and redirect JSONL to the test evidence folder.

```powershell
.\.venv\Scripts\python.exe -m scripts.studio_resource_baseline <test-production-id> --sample-seconds 600
```

The samples are interval observations and can miss shorter peaks. Use the saved image and motion receipts and the final timeline to separate inference, queue and render duration. Export a contact sheet and report from each completed production with `scripts.storyboard_quality_baseline`, and verify the saved images, clips and final MP4 with `scripts.studio_technical_qa`.

Record action coverage, count purposeful angles, and compare each adjacent segment boundary for subject, prop, pose and camera continuity. A technical pass leaves creative quality unverified. Frame chaining, conditioning and targeted regeneration require evidence from the resulting video before adoption.

## Lời thoại trong Studio (tùy chọn)

Trong storyboard, mở Nội dung & phiên bản → Âm thanh, chọn Windows SAPI hoặc Piper đã cài local. Piper cần tên file voice .onnx hợp lệ và JSON đi kèm; Windows có thể dùng voice mặc định hoặc tên đã cài. Không tải voice tự động. Sau khi Owner duyệt phiên bản mới, Studio dùng phụ đề từng cảnh làm lời thoại, tạo PCM WAV tạm, kiểm tra độ dài, pad khoảng im lặng đúng timeline, ghép AAC và kiểm tra decode. Nếu lời thoại dài hơn cảnh, production giữ ảnh/clip và báo cảnh cần rút ngắn; không tự cắt lời. Thay cấu hình âm thanh giữ checkpoint hình ảnh/chuyển động và tạo phiên bản mới. Receipt ghi nguồn, SHA, số mẫu và trạng thái decode; không khẳng định giọng đọc đúng ngôn ngữ hoặc chất lượng nghệ thuật. Chế độ đọc phụ đề không tự sinh nhạc hoặc hiệu ứng; dùng Audio Director khi cần lập cue và sinh âm thanh.

## AI Audio Director (pilot)

Trong Nội dung & phiên bản → Âm thanh, chọn engine local hoặc speech cloud, nhập voice mặc định và tùy chọn voice riêng cho nhân vật; chọn AI lập kế hoạch âm thanh. AI tạo cue lời thoại/thuyết minh độc lập với phụ đề, chọn vị trí frame, gain, và chọn WAV đã có trong thư viện local cho hiệu ứng, môi trường, nhạc. Đặt WAV PCM 16-bit mono/stereo hợp lệ trong workspace/audio-library, tên file ASCII dễ hiểu, tối đa 24 tài sản được đưa vào catalog. Mặc định không sinh nhạc/hiệu ứng mới. Nếu Owner bật tùy chọn sinh cloud và gán tuyến film.sound hoặc film.music cho profile ElevenLabs-compatible, AI có thể lập prompt sinh âm thanh khi không có WAV phù hợp. Adapter dùng API sound-generation hoặc music (MP3), không có model ID mặc định, chuyển PCM bằng FFmpeg, giới hạn lượt gọi và lưu SHA nguồn. Cue không có tài sản hay adapter được hiển thị riêng. Các WAV phải do Owner có quyền sử dụng. Cue được gắn SHA và timeline; file thay đổi hoặc timeline đổi cần lập lại kế hoạch. FFmpeg mix cue chồng nhau, có limiter, giữ chính xác số mẫu. Speech cloud dùng tuyến film.tts với profile OpenAI-compatible do Owner gán, voice ID do Owner nhập, tính ngân sách mỗi lượt trước dispatch, không tự fallback. Kiểm thử fixture không chứng minh API speech thật, giọng đọc hay mix nghệ thuật.

Tham chiếu API: [sound generation](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert) và [music](https://elevenlabs.io/docs/api-reference/music/compose/). Model, API key, quyền sử dụng và chi phí cần Owner xác minh; CI không gọi API thật.

## Xuất bản

**Status:** local release ledger, explicit Owner review, optional private-only YouTube OAuth CLI, signed video handoff, manual schedule intent and owner-recorded metrics **implemented in code/CI**. Real OAuth account, real private upload, platform analytics, and public scheduling are not verified.

### Safety contract

- Use only a verified Film Production render or an APPROVED Studio draft with its verified MP4, source SHA and render receipt SHA. Captions are included when available. The Owner must **watch the local MP4** and explicitly attest all content/music/voice rights; synthetic-media and kids declarations are Owner-provided booleans. Technical QA alone does **not** prove copyright, visual continuity or YouTube policy compliance.
- One immutable release per film episode, assigned UUID and SHA in local `data/company/film_publishing.sqlite3`. No script calls Google on prepare, inspect, attest or observe; the original MP4 is not copied or moved. Duplicate release attempts fail. File mutation invalidates release inspection.
- `planned_utc` is **only a local planning reminder**. Film Publishing has **NO automatic upload scheduler**, no YouTube `publishAt` call, no public/unlisted upload command, no advertising spend. Published/scheduled states in the local journal are Owner claims and not independent proof.
- Owner observation snapshots (views, likes, comments, watch minutes, UTC date) are **MANUAL** and have `platform_api_verified=false`. This is not a financial or YouTube monetization verification.
- The optional `youtube_private` adapter opens the official desktop OAuth browser once for each explicit upload. OAuth client JSON **must be outside the repo**; access/refresh credentials are held in memory, not saved to AgentForge. It uses `youtube.upload` scope, `videos.insert` resumable upload with `privacyStatus=private` and the Owner disclosure fields. Checkpoint to `UPLOAD_ATTEMPT_UNCERTAIN` before the external insert. On an ambiguous network/API result **never automatically retry**: manually check YouTube Studio, then Owner can record the matching video ID. The API response is not evidence that a private video is approved for public viewing.

Official API references: [videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert), [video status/privacy and scheduling constraints](https://developers.google.com/youtube/data/reference/rest/v3/videos), [desktop OAuth flow](https://developers.google.com/youtube/reporting/guides/authorization/installed-apps).

### Windows — setup and local handoff

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

Open `http://127.0.0.1:8780/dashboard/`, navigate to **Kênh xuất bản**. Select an approved Studio draft directly, or a manually assembled Film Production episode with a verified render receipt. The Dashboard reads the exact source and render SHA; Studio drafts do not need manual reassembly. Enter YouTube title/description, rights and watched confirmation, synthetic/kids disclosures and optional future ISO8601 timestamp (planning only). Click **Chuẩn bị handoff local (Private)**; inspect the new SHA receipt and local MP4/SRT paths. Nothing leaves your computer.

For manual upload, open YouTube Studio yourself and choose `episode.mp4`, attach `captions.srt` if appropriate, review disclosures, and set `Private`. After checking Studio, enter its **11-character video ID** and Owner-observed privacy state in Dashboard; statistics may be entered as manual snapshots. Do not interpret Owner-reported public/scheduled as platform verified.

### Optional real YouTube private-only OAuth upload

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

### Acceptance gates

CI runs full Python unittest, strict API Owner session/CSRF/sha gates, Dashboard build, OAuth client private payload contract, one-shot uncertainty, no local token persistence and ledger integrity tests, all with synthetic MP4 fixtures. **CI does not connect to YouTube or authorize a real Google account**.

Owner acceptance:
1. On Owner Windows PC, finish Motion and Film Production **real video** acceptance, review source MP4/audio/rights.
2. Prepare a local release with real source and receipt SHA; inspect handoff and verify no outgoing calls.
3. Optionally connect OAuth Desktop in local browser; upload a **private** video, view it in Studio, verify exact video ID and privacy. Confirm a network interruption does not trigger auto-retry.
4. Manually record publication schedule/status if changed on YouTube Studio. Never mark scheduled as platform-controlled by AgentForge.
5. Record optional Owner-observed statistics without inventing earnings from views.

Film Publishing code PASS does **not** mark a channel connected, earn money or publish a video automatically.

## Điều kiện nghiệm thu

CI Windows/React chỉ kiểm code, security contracts, fixture FFmpeg và static asset serving. Production GO đòi bằng chứng trên PC Owner với đúng commit.

1. Đăng nhập Dashboard localhost; xác nhận Owner session, CSRF và các route sản xuất video.
2. Ollama/ComfyUI model phải được kiểm bằng runtime thực, không suy từ cấu hình SQLite hay danh mục model đã phát hiện.
3. Tạo một shot motion có consent; kiểm graph, model hash, Comfy history, MP4 decode và SHA receipt; không blind retry.
4. Owner xem motion thật, continuity và nguồn âm thanh, quyền sử dụng.
5. Render episode với FFmpeg, phát lại và đối chiếu source/receipt SHA.
6. Chỉ tạo Publishing handoff khi Owner đã duyệt; private upload phải xác minh độc lập trong YouTube Studio.
7. Không xóa/migrate SQLite, workspace, model, secret, video trong cleanup Git.

## Phát hành trực tiếp từ Studio

Video mới ở trạng thái APPROVED xuất hiện trong màn hình Xuất bản. Kiểm tra phiên bản storyboard, receipt và SHA của MP4, sau đó xác nhận quyền sử dụng nội dung để tạo handoff trong cùng sổ phát hành. Không dựng lại bằng workflow thủ công. Có thể tải phụ đề đã xác minh từ Dashboard nếu tồn tại. Handoff và private upload CLI kiểm tra lại đúng nguồn Studio; không tự đăng, không tự upload và không khẳng định chất lượng thương mại.
