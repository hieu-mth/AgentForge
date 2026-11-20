# AgentForge — Local AI Video Studio

AgentForge là nền tảng video AI local-first (Python 3.13 + React/Ant Design), tập trung vào Film Studio, Character Registry, media generation, Model Hub và publishing handoff có xác nhận Owner. Các nghiệp vụ ngoài Studio không nằm trong runtime hiện hành.

## Chạy trên Windows

```powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Mở http://127.0.0.1:8780/dashboard/ và đăng nhập bằng mã Owner được in riêng tại terminal. Model Hub khởi tạo với **không model nào được đăng ký**; Owner thêm và phân công model qua Dashboard. Capability metadata nằm trong Python, không còn thư mục `config/`. Chỉ bật `--allow-external-tools` khi chủ động chạy các tác vụ media đã review. Ứng dụng không tự cài ComfyUI, tải weights, kích hoạt GPU hay public YouTube.

## Hướng dẫn

- [Phát triển và CI](docs/DEVELOPMENT.md)
- [Cấu trúc nền tảng](docs/architecture/REPOSITORY_STRUCTURE.md)
- [Film Studio](docs/architecture/LONG_FORM_AI_FILM_STUDIO.md)
- [Motion ComfyUI 12 GiB](docs/verification/MOTION.md)
- [Production/FFmpeg](docs/verification/PRODUCTION.md)
- [Publishing handoff](docs/verification/PUBLISHING.md)
- [Owner runtime acceptance](docs/verification/OWNER_PRODUCTION_GATE.md)

Git cleanup **không xóa hay migrate** `data/`, `workspace/`, `.env`, model weights, secrets, video và backups của Owner. AgentForge không cần file `.env` để khởi động; source không tự nạp `.env`, nhưng file này vẫn được Git ignore để tránh lộ secrets. CI fixture không chứng minh GPU, continuity, voice hay upload thật.

### Kiểm thử bộ nhớ Studio với ba bản nháp

Khi Ollama và ComfyUI đang chạy và Model Hub đã gán các năng lực local, dùng một lúc máy rảnh để chạy:

```powershell
.\.venv\Scripts\python.exe scripts/check_draft_resources.py --confirm-local-inference
```

Lệnh tạo ba bản nháp liên tiếp bằng model thật trong workspace kiểm thử riêng. So sánh các dòng cuối mỗi clip trong `samples.jsonl` và các mốc trước/sau từng bước trong `clip-*.json`. Số liệu gồm RAM khả dụng, commit của Windows, VRAM, working set và private bytes theo tiến trình nhận diện được. Chạy thử dashboard song song nếu cần kiểm tra tab trình duyệt. Chỉ coi kiểm thử live đạt khi cả ba MP4 qua xác minh và tab hoạt động như mong đợi.

Worker Studio xử lý một bản nháp mỗi lượt, mặc định giới hạn ba job đang chạy hoặc đang chờ. Có thể đặt `AGENTFORGE_DRAFT_QUEUE_LIMIT` từ 1 đến 8 khi khởi động backend. Khi thiếu tài nguyên, job dừng ở checkpoint và có thể tiếp tục bằng nút **Tiếp tục từ checkpoint**. Yêu cầu hủy đang chạy có hiệu lực tại checkpoint kế tiếp.
