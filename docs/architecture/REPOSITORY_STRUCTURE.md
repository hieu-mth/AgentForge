# Kiến trúc AgentForge Video Studio

\`\`\`text
agentforge/
  api/           # Owner-auth localhost HTTP, CSRF, feature endpoints
  ai/            # Model registry + Model Hub, no implicit model execution
  features/
    film_studio/  # characters, long_form, motion, production, publishing
    media/        # visual jobs, Comfy image, FFmpeg, MP4 validation
  integrations/  # ComfyUI loopback, optional YouTube private upload
  ops/           # read-only environment discovery, runtime evidence
  paths.py       # canonical path, symlink/junction checks
  ops_control.py # pause/resume owner-gated actions
dashboard/       # React/Ant Design
config/          # model profiles, film/image routes
examples/film_studio/
scripts/         # Windows setup, preflight and source/docs hygiene
tests/           # only current video/security tests
\`\`\`

Film Studio giữ SHA-bound receipts và explicit Owner approval. GPU tasks, external subprocess/YouTube upload không tự chạy khi truy cập GET/UI. Các đường code Website/Webapp/Growth/Goal/Skill/Worker legacy đã nghỉ được xóa, không giữ alias chỉ để tương thích.

\`data/\`, \`workspace/\`, \`.env\`, \`models/\` thuộc Owner, ngoài phạm vi xóa. Không có migration tự động đối với historical SQLite.
