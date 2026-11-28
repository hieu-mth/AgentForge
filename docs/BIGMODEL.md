# BigModel — CogVideoX-Flash

Model AI → Đăng ký model → Cloud → BigModel (Zhipu AI). Model ID `cogvideox-flash`, endpoint `https://open.bigmodel.cn/api/paas/v4`. Enter the complete standard API key (`id.secret`) in the dashboard, or configure BIGMODEL_BASE_URL and BIGMODEL_API_KEY in the terminal. The registry does not create a default model or store plaintext keys.

Use Chạy thử with a short prompt to submit one job, then poll the existing probe until verified. For production assign film.motion and enable the necessary permissions. Assigned or automatic routing supports direct text-to-video and image-to-video through the existing image route. Cloud seconds are derived from the reviewed timeline.

Conservative pilot contract: 5-second source clips, normalized 1280×720 at 24 FPS, no native audio, 512-character prompts; image input PNG/JPEG up to 5 MiB, raw Base64. The Flash request does not send duration, size, fps, or audio options; those parameters have not been certified on the actual account. Source clips shorter than the contract fail verification rather than padding. No automatic POST retry; reconcile uncertain submissions before another attempt. HTTPS asset download checks public addresses, pins DNS and TLS, disallows redirects, bounds bytes, and verifies output locally. Provider pricing and account quotas remain Owner checks.

Official API: https://docs.bigmodel.cn/cn/guide/models/free/cogvideox-flash

The user has verified direct API submission; full live dashboard and I2V acceptance remain unverified.
