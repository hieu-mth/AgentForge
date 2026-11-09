# Model Hub — quản lý AI Providers, Models và Routing

**AgentForge Base V1 · M6 + M7 · 09/11/2026**. Giao diện: **Cài đặt → AI Models & Routing**, đường dẫn `http://127.0.0.1:8780/dashboard/#/models`.

Model Hub giúp chọn model phù hợp với tác vụ **text/code đang có runtime**, và lưu cấu hình trước cho **image/video**. Cấu hình thành công **không chứng minh model đã cài, API key hoạt động, đủ VRAM hoặc tạo được video**.

## 1. Nguồn dữ liệu chính thống

```text
config/models.toml               # Model text mặc định: Ollama / Anthropic
workers/<id>/worker.toml         # Default model cho mỗi worker
config/task_routes.toml          # Task ID, loại capability, mức tích hợp
              │
              v
agentforge/ai/model_hub.py       # Hợp nhất default + override, kiểm tra chính sách
              ^
              │
data/company/model_hub.sqlite3   # Owner overrides, revision & rollback, gitignored
              │
              v
agentforge/model.py              # LLM text runtime (chỉ route "wired")
              ^
Dashboard → Settings → Models  # Owner consent + CSRF + revision
```

**Độ ưu tiên lúc LLM chạy:** `AGENTFORGE_MODEL_REF` đặt tường minh trong process → Owner route override trong SQLite → worker `model_ref` trong TOML → `local_primary` cho general. Không tự thay provider hoặc fallback qua cloud. Các route video/image chưa kết nối tới adapter render.

## 2. Provider / Model / Task là ba thực thể khác nhau

| Loại | Ví dụ | Ý nghĩa và giới hạn |
| --- | --- | --- |
| Provider | `ollama` | Local HTTP text API |
| Model profile | `local_primary` → `qwen3:8b` | Name, endpoint, enabled, provider; chưa chắc online |
| Task route | `web.create` → `local_primary` | Text worker sẽ dùng profile khi được quyền gọi model |
| Cloud profile | `cloud_primary` | Cloud HTTP endpoint/key chỉ **tham chiếu tên biến môi trường**, không lưu token |
| Video profile | `wan_video` + `comfyui` | **CONFIG_ONLY**; chưa áp vào Film Studio render |
| Operations | `ops.monitor` | Python rules, không cần AI |

**Trạng thái:**
- `ROUTED`: mapping hợp lệ và text runtime đã nối; không khẳng định model health.
- `CONFIG_ONLY`: image/video/film storyboard được gán trên UI nhưng code render chưa tiêu thụ route.
- `UNCONFIGURED`: chưa có lựa chọn.
- `DETERMINISTIC`: không gọi LLM.
- `INCOMPATIBLE`, `INVALID_CONFIG`: phải sửa config trước.

Profile mặc định có `health=UNVERIFIED`. Nút **Kiểm tra** chỉ dành cho Ollama, chủ động gửi một `GET /api/tags` tới **loopback đã xác thực**, timeout 3 giây, giới hạn 256 KB. Không inference, không download/GPU, không kiểm tra hoặc xác minh chi phí cloud. Với ComfyUI/Anthropic, trạng thái probe là `NOT_CHECKED` (không làm network probe).

## 3. Các hành động trên Dashboard

- **Đăng ký/Sửa model:** điền profile ID, provider, model/checkpoint ID và endpoint local hoặc tên biến môi trường cloud; hệ thống không có input API key.
- **Gán route:** chọn model được bật và phù hợp capability, xem rủi ro cloud/GPU, bấm **Lưu route** và xác nhận Owner.
- **Reset:** xóa override của đúng một route, trở về default Git/worker TOML.
- **Hoàn tác:** khôi phục snapshot ở revision trước và ghi một revision mới; không xóa lịch sử.
- **Kiểm tra:** chỉ đọc metadata Ollama local, có xác nhận; không thay routing.

## 4. Bảo mật và audit

| API | Method | Bảo vệ |
| --- | --- | --- |
| `/api/model-hub` | GET | Owner session, read-only |
| `/api/model-hub/profile` | POST | `SAVE_MODEL_PROFILE`, exact fields, CAS revision |
| `/api/model-hub/route` | POST | `SET_MODEL_ROUTE`, capability allowlist, CAS revision |
| `/api/model-hub/reset` | POST | `RESET_MODEL_ROUTE`, CAS revision |
| `/api/model-hub/rollback` | POST | `ROLLBACK_MODEL_HUB`, snapshot history |
| `/api/model-hub/check` | POST | `CHECK_LOCAL_MODEL`, GET localhost metadata only |

Mọi POST đi qua **Host/Origin, Owner cookie, CSRF, exact ack** hiện hành. SQLite dùng `BEGIN IMMEDIATE`, `expected_revision` chống lost update. Dữ liệu Owner ở `data/company/model_hub.sqlite3` không commit Git; chỉ lưu model metadata và route, **không lưu token, prompt, generated code**.

Chọn cloud qua Dashboard **không cấp quyền chi tiền**: khi runtime dùng saved cloud route vẫn yêu cầu `AGENTFORGE_CLOUD_MODEL_CONSENT=YES` ở process và các quyền model.invoke của task. Legacy explicit process override `AGENTFORGE_MODEL_REF` được giữ tương thích như trước; không tự fallback.

`model.resolve_runtime()` trả thêm `routing_revision` và `route_source`. **Chưa tự ghi đủ model-provenance cho toàn bộ job ledger**; cần bổ sung ở đợt skill/job hardening sau này. Không lấy route snapshot làm bằng chứng provider billing.

## 5. Kiểm thử trên Windows

```powershell
cd D:\AgentForge
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m unittest tests.test_model_hub -v
npm.cmd test --prefix dashboard
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

CI thử SQLite rollback/CAS, Host/Origin/CSRF, ngăn URL ngoài/secret, cloud consent, Model UI helpers và Edge browser với fixture. **Không chạy Wan/ComfyUI thực hoặc API trả phí**.

**Ngoài scope M6/M7:** tự cài checkpoint, tự tạo video, inference trên GPU, tự đăng YouTube, auto billing, chuẩn hóa skill handlers M8 và toàn bộ job provenance. Những việc đó cần test và quyền riêng.
