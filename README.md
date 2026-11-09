# AgentForge

**Local-first AI Product Studio** — hệ thống Python + React để Owner giao việc cho AI, tạo bản nháp sản phẩm, quản lý workflow và xét duyệt artifact theo bằng chứng.

> **Trạng thái: bản thử nghiệm dùng nội bộ.** CI xác minh code đáng tin cậy; không có bằng chứng rằng mọi ứng dụng/phim do AI sinh ra đều chạy đúng, sẵn sàng thương mại hoặc đã tạo doanh thu.

## Setup an toàn (M9)

Chạy kiểm tra read-only trước: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1`. Để cài dependency và build Dashboard, dùng `-Install -AllowNetwork` (cho phép pip/npm truy cập registry), xem [hướng dẫn](docs/DEVELOPMENT.md). Xem kết quả trong Dashboard → Cài đặt → Vận hành; các checks không tự gọi model/GPU.

## Bắt đầu nhanh trên Windows

Yêu cầu: **Python 3.13+**, Node.js 22 và npm. Mở PowerShell tại repository:

~~~powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
~~~

Mở **http://127.0.0.1:8780/** (chuyển đến `/dashboard/`), sau đó sử dụng mã Owner in ra trong PowerShell. Giữ cửa sổ chạy server, nhấn `Ctrl+C` để dừng.

Nếu báo không tìm thấy `.venv\Scripts\python.exe`, chạy `py -0p` để kiểm tra phiên bản Python trước khi tạo lại môi trường. Không bắt buộc Docker cho việc phát triển thông thường.

## Hiện có những gì?

| Mảng | Khả năng đang có | Giới hạn quan trọng |
| --- | --- | --- |
| **Dashboard & workflow** | React Dashboard, task/goal, Owner approval, SQLite, lịch sử và SHA | Chỉ vận hành local cho một Owner; không phải SaaS |
| **Model Hub** | Chọn model text/code theo tác vụ, lưu SQLite revision/rollback; Dashboard quản lý profiles | Video/Image chỉ config-only, cloud cần quyền Owner |
| **Website Builder** | Thiết kế website theo schema có giới hạn; feedback sinh phiên bản đề xuất | Không phải công cụ tạo full-stack tùy ý |
| **Marketplace** | NovaMart demo, lọc/tìm kiếm/giỏ hàng, catalog do AI đề xuất | Không có thanh toán, backend bán hàng thật |
| **AI React Developer** | Đề xuất source JSX/CSS và kiểm tra cú pháp | Chưa sửa source AI qua feedback; build/browser QA AI chưa xác minh |
| **AI Film Studio** | Lập kế hoạch phim dài và adapter gửi shot ComfyUI theo quyền Owner | **Chưa kiểm chứng render video động thật trên GPU 12 GB**, chưa tự dựng phim dài |
| **Media / Growth** | Ảnh tĩnh, SRT, TTS tùy chọn, FFmpeg MP4, gói bàn giao | YouTube upload vẫn thủ công; không có doanh thu tự xác minh |

Chi tiết và định nghĩa trạng thái: **[Current Status](docs/STATUS.md)**. Base V1 technical readiness: [Wave 5 Owner acceptance](docs/verification/base_v1/README.md); CI PASS không có nghĩa máy/model thật đã nghiệm thu.

## Điều hướng tài liệu

- **[Trung tâm tài liệu](docs/README.md)** — bắt đầu từ đây, phân biệt docs hiện hành và lịch sử.
- **[Hướng dẫn Windows & kiểm thử](docs/DEVELOPMENT.md)** — setup, build, chạy Dashboard và các giới hạn an toàn.
- **[Roadmap hiện hành](docs/ROADMAP.md)** — ưu tiên AI Source Revision và AI Film Studio.
- **[Kiến trúc repository đang chạy](docs/architecture/REPOSITORY_STRUCTURE.md)** — module nào thực sự đang chạy.
- **[Model Hub M6/M7](docs/architecture/MODEL_HUB.md)** — cấu hình provider/model/task routing trên Dashboard.
- **[Skill Engine M8](docs/architecture/SKILL_ENGINE.md)** — code-owned permissions và adapter theo domain.
- **[Feature Boundaries M4](docs/architecture/FEATURE_BOUNDARIES.md)** — nơi đặt code mới, compatibility và tích hợp ComfyUI.
- **[Compatibility M5](docs/architecture/COMPATIBILITY_POLICY.md)** — root aliases tới features và quy tắc cleanup an toàn.
- **[API contract M0/M3](docs/architecture/API_CONTRACT_V1.md)** — Owner login, CSRF, routes và compatibility.
- **[Cấu trúc đã chốt (M1–M4)](docs/architecture/TARGET_STRUCTURE.md)** — Python/React ở root, các feature canonical đã chuyển.
- **[Giải thích từng file Python/React](docs/architecture/FILE_CATALOG.md)** — inventory 200 module Python và Dashboard.
- **[Templates](templates/README.md)** và **[Examples](examples/README.md)** — phân biệt template runtime với file JSON mẫu.
- **[AI Film Studio 12 GB](docs/architecture/FILM_MOTION_12GB_PILOT.md)** — điều kiện cần trước khi tạo clip thật.
- **[Bằng chứng Phase 1](docs/verification/phase1/README.md)** — snapshot kiểm thử, không phải trạng thái live.

## Nguyên tắc vận hành

- Chỉ phục vụ Dashboard ở localhost; `/` redirect tới `/dashboard/`. Giao diện HTML/JS V0 đã xóa.
- **Không thực thi source do AI sinh ra trên Windows host** khi chưa có sandbox được kiểm chứng.
- Không tự sử dụng API trả phí, đăng YouTube hay public sản phẩm khi chưa có quyền và bằng chứng.
- `data/`, `workspace/`, `.env`, các model và backup là dữ liệu của Owner: **không dọn/xóa tự động**.
- Chỉ xem một lần test PASS là xác minh đúng phạm vi của test, không phải nghiệm thu phim/app ngoài thực tế.

Mã nguồn: `agentforge/` (backend), `dashboard/` (frontend), `skills/`, `workers/`, `tests/`. Repository đã loại bỏ frontend V0; những compatibility module còn được sử dụng vẫn phải được giữ.
