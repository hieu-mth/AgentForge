# Kiến trúc AgentForge Video Studio

```text
agentforge/
  api/           # Owner-auth localhost HTTP, CSRF, feature endpoints
  ai/            # SQLite Model Hub + source capability policy, no implicit execution
  features/
    film_studio/  # characters, long_form, motion, production, publishing
    media/        # visual jobs, Comfy image, FFmpeg, MP4 validation
  integrations/  # ComfyUI loopback, optional YouTube private upload
  ops/           # read-only environment discovery, runtime evidence
  paths.py       # canonical path, symlink/junction checks
  ops_control.py # pause/resume owner-gated actions
dashboard/       # React/Ant Design
examples/film_studio/
scripts/         # Windows setup, preflight and source/docs hygiene
tests/           # only current video/security tests
```

Film Studio giữ SHA-bound receipts và explicit Owner approval. GPU tasks, external subprocess/YouTube upload không tự chạy khi truy cập GET/UI. Không giữ alias của sản phẩm đã nghỉ chỉ để tương thích ngược.

Model profiles, model-route assignments và chính sách AI điều phối được lưu ở `data/company/model_hub.sqlite3` (Owner-managed). Một checkout mới không có model mặc định. Catalog capability chỉ nằm trong Python; `config/` đã bị loại bỏ.

`data/`, `workspace/`, `.env`, `models/` thuộc Owner, ngoài phạm vi xóa. Không có migration tự động đối với historical SQLite. Không có `.env` auto-loader; Windows/process environment vẫn có thể được dùng cho tham chiếu secret nếu Owner cần.
