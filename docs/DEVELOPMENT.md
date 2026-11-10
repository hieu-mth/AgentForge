# Phát triển và vận hành trên Windows

> **Đường dẫn hiện tại: `agentforge/` (Python) và `dashboard/` (React), đều ở repository root.** [M1+M2](architecture/MIGRATION_PLAN.md) đã chuyển, M3 đã chia API; M8 chia skill adapters; M4a–M4d2 đã chuyển Growth/Website/Webapp/Media/Film canonical features và HTTP ComfyUI transport. ComfyUI transport đã tách tại M4d2; M4 research/ops còn review; M5 phase 1 đã chuyển 22 root aliases thẳng vào features + audit, xóa aliases phase 2 còn chờ.

**Đối tượng:** Owner/developer làm việc trực tiếp tại `D:\AgentForge`. Có thể dùng folder khác; các lệnh bên dưới giả định repo đã clone.

## 0. Setup nhanh, có phân biệt read-only và install

```powershell
cd D:\AgentForge
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

Mặc định chỉ kiểm tra môi trường (Python, Node/npm, cấu hình, Dashboard build); **không** gọi mạng, cài package, chạy model hoặc xóa file. Với venv và Node.js 22 đã cài sẵn, muốn cài dependencies/build lại bằng lệnh thủ công có xác nhận:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -Install -AllowNetwork
```

`-Install -AllowNetwork` cho phép pip/npm liên hệ package registry và ghi **chỉ vùng code/caches** `.venv/`, `dashboard/node_modules/`, `dashboard/dist/`; không chạm `data/`, `workspace/`, `.env`. Script không cài Docker/GPU model/ComfyUI, không tạo Windows service, không chạy AI-generated source. Có thể thêm `-RunTests` để chạy Python + Dashboard unit tests hoặc `-StartDashboard` để chạy foreground (chỉ hợp lệ khi Install).

Dashboard `Cài đặt → Vận hành` có bảng kiểm tra local từ `/api/ops/preflight` và `/api/ops/health`. Đây là kết quả đọc-only và cần Owner login; nó không tự sửa lỗi.

## 0b. Nghiệm thu Base V1 (Đợt 5)

```powershell
.\.venv\Scripts\python.exe -B -m agentforge.ops.base_acceptance
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunContractTests
```

Các lệnh này kiểm tra local readiness và chạy **trusted fixture tests**; không chứng minh model/GPU thật. Sau khi Owner đồng ý và có database cần backup, tùy chọn `-CreateBackup -StageRestore` (ZIP và staging **không mã hóa**, giữ lại để Owner đối chiếu, không tự ghi đè dữ liệu). Xem [checklist nghiệm thu thực tế](verification/base_v1/README.md).

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
.\.venv\Scripts\python.exe scripts/compat_audit.py --check
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

## 7. V5 Owner workflow: duyệt theo bước, retry và xem sản phẩm

- Trong **Giao việc → Kế hoạch & phê duyệt**, mỗi lần **Chạy/Tiếp tục** chỉ yêu cầu
  các quyền của bước hiện tại (Architect, Developer, QA tĩnh, Reviewer). Tên bước,
  chỉ số và trạng thái thực thi xuất hiện trước khi xác nhận. Một lượt chạy không
  tự cho phép các bước gọi model kế tiếp.
- Nếu V5 có child task ở trạng thái **FAILED** rõ ràng, nút
  **Chuẩn bị chạy lại bước N** sẽ mở lại *đúng bước lỗi* sau khi Owner duyệt
  mã SHA và task ID. Đây chỉ là thao tác chuẩn bị; bấm chạy tiếp vẫn cần cấp
  lại quyền model/công cụ. Task FAILED cũ giữ nguyên trong lịch sử và event
  `STEP_RETRY_ARMED` lưu ID cũ để kiểm toán. Bước thành công không bị chạy lại.
- **INTERRUPTED**, `DISPATCHING` và quality gate thất bại không có child
  task FAILED rõ ràng **không được tự retry**; Owner cần kiểm tra trạng thái
  và tác dụng phụ trước. Không xóa dữ liệu để ép chạy lại.
- Ngay sau bước Developer thành công, kể cả khi QA/Reviewer chưa xong hay
  báo lỗi, có thể chọn **Xem source sản phẩm ngay**. Trang duyệt proposal cho
  xem mã nguồn và, nếu đã có bằng chứng, ảnh desktop/mobile từ Chromium QA
  offline có SHA khớp proposal. Chưa có ảnh phải chạy riêng QA Chromium trong
  Docker với sự cho phép của Owner. Không thực thi JSX do AI sinh trong Dashboard
  hoặc trên Windows host; ảnh smoke-test không thay thế kiểm thử tương tác.
- Lưu source, review, QA và nghiệm thu là các trạng thái riêng; không tự deploy.

Kiểm tra hồi quy:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_v5_company tests.test_control_center_v1 -v
npm.cmd run build --prefix dashboard
```

## 8. Phát video MP4 local trực tiếp trên Dashboard

Vào **Đánh giá → Video local → Xem video** cho production đã render
(`VIDEO_READY`) hoặc đã duyệt (`APPROVED`/`REJECTED`). Trình phát HTML5
có Play/Pause, âm lượng, tua và toàn màn hình. File tiếp tục nằm tại
`workspace/media/<run_id>/video.mp4`, **không upload lên cloud**.

API `GET /api/videos/<production_id>/stream` yêu cầu phiên Owner đăng nhập
và việc mở thông tin production trước đó trong cùng phiên. Server kiểm tra
QA hiện tại, dấu SHA và nguồn local hợp lệ, trả video theo byte range
(`206 Partial Content`) bằng các chunk 64 KiB. Range không hợp lệ được
trả `416`. Không nhận đường dẫn file tùy ý hoặc phát source chưa kiểm chứng.
Trình phát không tự nghiệm thu; Owner cần xem/nghe rồi tự xác nhận.

Kiểm thử logic streaming:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_video_stream -v
npm.cmd run build --prefix dashboard
```

## 9. Từ AI storyboard sang video MP4 trong Dashboard

Quy trình local-first: **Giao việc → Xem kết quả storyboard → Bước 2A: Tạo
tư liệu → Bước 2B: Render MP4 → Đánh giá → Video local → Xem video**.

Bước 2A chỉ khả dụng sau khi Owner mở đúng task `media.copy_draft` thành công.
`GET /api/tasks/<task_id>` ghi nhận SHA-256 của storyboard đã xem trong
session; `POST /api/media/prepare-from-task` phải chứa `ack:
PREPARE_REVIEWED_STORYBOARD`, `task_id`, `source_sha`. Backend **tự lấy**
nội dung từ task history, không tin vào JSON gửi bởi trình duyệt; kiểm tra SHA,
loại task, status và media schema, tạo `slug` mới, gọi lại local `media.compose`
và kiểm tra QA. Cần cấu hình business profile của Owner trước khi prepare.

Bước 2B dùng `POST /api/videos/<production_id>/render` với `ack:
RENDER_LOCAL_MP4` và `storyboard_sha`. Phải bật external tools khi khởi động
backend; server xác thực SHA và production status rồi mới cho phép FFmpeg chạy
**một lần duy nhất**. Không tự render ở bước 2A; không retry production chưa rõ
trạng thái, không ghi đè artifact, không tự xuất bản. Nếu đóng Dashboard sau 2A,
vào **Đánh giá → Video local** để render production `ASSETS_READY`.

Khi render xong, production chuyển `VIDEO_READY` và có thể mở trình phát MP4
được xác thực bằng session. Render/QA hoàn tất không có nghĩa Owner đã nghiệm thu.
Phần này tạo video **tĩnh từ PNG + WAV + phụ đề**, không hứa tạo chuyển động AI.

Test API logic (không chạy model/FFmpeg):

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_media_dashboard_flow tests.test_media_workflow_v15 -v
npm.cmd run build --prefix dashboard
```

## 10. Media Standard V2 — ảnh AI theo từng shot và chuyển động camera

Trong **Giao việc → Kết quả storyboard → Bước 2A**, chọn **Studio** để dùng
một ảnh AI riêng cho mỗi cảnh. Gallery chỉ hiện các job ComfyUI trong Image
Studio đã được `collect` vào local (`ASSET_READY`/`ATTACHED`). Có thể xem
thumbnail bằng API preview hiện có, chọn lại ảnh từng shot và chọn camera
`slow_zoom`, `slow_pan` hoặc `static`. Không download, không tự submit
ComfyUI và không tự gọi model trong thao tác prepare.

Từ gallery, backend kiểm tra từng ID job, receipt SHA và PNG thật trước khi
rasterize. Ảnh ngang được giữ nguyên chủ thể trong hero, dùng nền blur phía
sau và typographic layout phù hợp khung 9:16, thay vì chỉ thay màu gradient.
Sau `ASSETS_PASS`, **Bước 2B** cần Owner xác nhận riêng để FFmpeg thực hiện
camera movement khi render. Cấu hình hình ảnh và motion được lưu trong manifest
cùng SHA từng ảnh đầu vào và đầu ra. Các video cũ không có `visual_plan` vẫn
chạy kiểu Classic/static như trước.

Nếu chưa có đủ ảnh AI riêng cho từng cảnh, Dashboard ghi rõ chế độ **Classic**
là template cũ; không được nhận là tạo hình AI. Muốn Studio phải tạo/thu thập
đủ ảnh qua Image Studio trước. Chế độ Studio không tự dựng video chuyển động
bằng video model, không voiceover tự động và không tạo ảnh mới từ prompt ở
lượt này. Cinematic/video model phải dùng pipeline riêng có review nguồn,
GPU quota và quyền Owner; không tự kích hoạt.

Kiểm thử:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_s2_media tests.test_media_dashboard_flow tests.test_media_workflow_v15 -v
npm.cmd run build --prefix dashboard
```
