# Phát triển và vận hành trên Windows

> **Đường dẫn hiện tại: `agentforge/` (Python) và `dashboard/` (React), đều ở repository root.** [M1+M2](architecture/MIGRATION_PLAN.md) đã chuyển, M3 đã chia API; M8 chia skill adapters; M4a–M4d1 đã chuyển Growth/Website/Webapp/Media/Film canonical features. ComfyUI transport đã tách tại M4d2; M4 research/ops và cleanup aliases (M5) vẫn chờ.

**Đối tượng:** Owner/developer làm việc trực tiếp tại `D:\AgentForge`. Có thể dùng folder khác; các lệnh bên dưới giả định repo đã clone.

## 1. Chuẩn bị

- Python **3.13+**: chạy `py -0p` để xác minh.
- Node.js **22** và npm: `node --version`, `npm.cmd --version`.
- Không cần Docker chỉ để chạy Dashboard, Python tests, static builder và phát triển code đáng tin cậy.
- Không sửa hoặc xóa `data/`, `workspace/`, `.env` và backup khi cleanup.

~~~powershell
cd D:\AgentForge
git status --short
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
~~~

Nếu venv đã tồn tại, bỏ qua bước tạo lại. Nếu `py -3.13` không có, kiểm tra `py -0p` rồi dùng Python 3.13+ thật sự được cài. Không giả định file `.venv\Scripts\python.exe` luôn có sẵn.

Nếu vừa cập nhật từ cấu trúc cũ, Git chuyển `ui/dashboard/` → `dashboard/` và `src/agentforge/` → `agentforge/`. Cache local cũ vẫn được gitignore; **không xóa cache/SQLite để hoàn thành migration**. Sau `git pull`, cài lại Python editable package bằng `python -m pip install -e ".[media]"` trong venv, đồng thời chạy `npm ci` tại `dashboard/`, để không dùng nhầm source path đã đổi.

## 2. Chạy Dashboard

~~~powershell
.\.venv\Scripts\python.exe -m agentforge --port 8780
~~~

Truy cập **http://127.0.0.1:8780/**. Root sẽ chuyển tới `/dashboard/`. Mã đăng nhập Owner được in trong cửa sổ PowerShell; `Ctrl+C` để tắt.

Chỉ khi thực sự cần các công cụ bên ngoài và đã duyệt quyền:

~~~powershell
.\.venv\Scripts\python.exe -m agentforge --port 8780 --allow-external-tools
~~~

Cờ này không cho phép tùy tiện public hệ thống hay chạy generated code. Server và Vite phải chỉ lắng nghe loopback.

## 3. Kiểm thử an toàn

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/check_docs.py
npm.cmd run test:navigation --prefix dashboard
npm.cmd run build --prefix dashboard
npm.cmd ci --prefix templates/novamart --ignore-scripts --no-audit --no-fund
npm.cmd test --prefix templates/novamart
npm.cmd run build --prefix templates/novamart
~~~

Browser smoke của Dashboard/NovaMart chạy trên Microsoft Edge nếu máy đã có Edge và prerequisites. CI dùng Windows, Python 3.13 và Node 22.

**Không cài npm dependencies hoặc chạy build/script của AI-generated source trực tiếp trên host Windows**. React AI cần sandbox và QA riêng; source syntax check không chứng minh runtime.

## 4. Film Studio GPU 12 GB

Bản hiện tại có Film planner và adapter ComfyUI localhost, **chưa có model Wan 2.2 tích hợp sẵn**. Môi trường của Owner chưa được xác minh từ CI.

Kiểm tra kết nối (không chạy inference):

~~~powershell
.\.venv\Scripts\python.exe -m agentforge.domains.media.motion_comfy health
~~~

- Film planner: [long-form spec và CLI](architecture/LONG_FORM_AI_FILM_STUDIO.md).
- Kiểm tra workflow trước khi chạy GPU: [12 GB motion pilot](architecture/FILM_MOTION_12GB_PILOT.md).
- Bộ phim mẫu 2 giờ có shot 8 giây **không đủ điều kiện** cho adapter pilot 4 giây. Cần kế hoạch pilot riêng.
- Không gắn nhãn “motion complete” khi chưa có MP4 decode/QA và số đo VRAM/thời gian thực tế.

## 5. Đồng bộ repository

~~~powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main
~~~

Nếu `git status` có thay đổi local chưa commit, cần đối chiếu trước khi pull. **Không** dùng `git clean -fdx`, `git reset --hard`, hoặc xóa đệ quy trên folder Owner.

## 6. Tìm nguyên nhân lỗi phổ biến

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Không có `.venv\Scripts\python.exe` | `py -0p`; tạo lại venv bằng Python 3.13 |
| Dashboard 404 / asset thiếu | `npm.cmd ci` và `npm.cmd run build --prefix dashboard` |
| Không thấy ComfyUI | Kiểm tra service local `127.0.0.1:8188`, không mở cổng ra Internet |
| Motion job báo `UNVERIFIED` | Đây là trạng thái đúng khi chưa có clip QA, không phải tự động PASS |
| CLI model/worker lỗi | Kiểm tra `config/`, `workers/`, quyền Owner và model được enable |
