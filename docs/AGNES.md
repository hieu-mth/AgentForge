# Agnes Flash integration

Register two Cloud profiles in Model AI, choose Agnes AI and the official endpoint
`https://apihub.agnes-ai.com/v1`. Model IDs: `agnes-image-2.5-flash` and
`agnes-video-2.5-flash`. Use the encrypted key or the AGNES_BASE_URL and AGNES_API_KEY
environment variables. Assign image.generate / film.motion in AI orchestration and
explicitly approve cloud calls and a production seconds budget.

Reference: https://github.com/AgnesAI-Labs/skills/blob/main/agnes-ai-models/references/model_catalog.md

The shared cloud video contract currently normalizes to 720p / 24 FPS, 4–10 seconds
for Agnes, without native audio. Image output is requested at 1K and verified as PNG.
Unknown POST outcomes are not automatically retried. Promotions and quota are not
verified by this adapter. Real account inference remains an Owner acceptance test.

## Dashboard test

Open **Model AI → Chạy thử** for an enabled Agnes media profile. Enter a test
prompt; the action explicitly authorizes one image or one four-second video.
Use the same probe ID to poll the existing video; it never submits again.
Probe image and video previews are served locally after verification. Cloud
billing and account entitlement remain unverified until the Owner runs a test.

## Cloud error handling

Agnes HTTP 503 with the exact `video_queue_full` code, or HTTP 429, is treated as a rejected submission when no job evidence is returned. Studio reserves the original seconds budget once, counts every HTTP submission against the cloud-call cap, and retries the same shot at 60/120/300 seconds (honoring longer numeric Retry-After up to 900 seconds). The worker waits outside the dispatch guard; it does not regenerate images or verified clips. The retry deadline and rejection are persisted. After backend restart, explicitly resume the waiting production. Permanent rejections display sanitized HTTP status; no automatic retry. Unclassified 5xx, malformed success responses, and transport failures remain uncertain. Old ambiguous records are not automatically reclassified. An explicitly approved retry of a rejected request keeps its original seconds reservation; confirmed remote failures use a new reservation. All calls count against the lifetime cap. Probes never automatically submit again.
