# Phát triển AgentForge Video Studio trên Windows

Đây là hướng dẫn **source hiện hành**, không phải tài liệu các milestone Webapp/NovaMart/Business cũ. AgentForge là local-first, một Owner, Python 3.13 và React/Ant Design (Node 22).

## Cài đặt và chạy Dashboard

~~~powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
~~~

Mở `http://127.0.0.1:8780/dashboard/`. Server chỉ bind `127.0.0.1`; mã đăng nhập Owner được hiển thị tại console. Không lưu mã hoặc token vào repository. Để phát triển frontend, chạy `npm.cmd run dev --prefix dashboard`; API production vẫn yêu cầu session Owner/CSRF.

## Kiểm chứng source và UI

~~~powershell
.\.venv\Scripts\python.exe scripts/check_docs.py
.\.venv\Scripts\python.exe scripts/check_source_hygiene.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd run test:navigation --prefix dashboard
npm.cmd run build --prefix dashboard
npm.cmd run test:browser --prefix dashboard
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunContractTests
~~~

Nên kiểm tra CI Windows/Node22/Python3.13 trên GitHub sau mỗi nhóm refactor. Bản chạy với fixture không chứng nhận inference/GPU/video thật. Tuyệt đối không dùng `git clean -fdx` hay `reset --hard` để dọn local data.

## Chứng nhận runtime riêng trên máy Owner

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunFFmpeg -ConfirmLocalExec -SaveReport
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.motion_comfy health
~~~

Preflight mặc định không gọi model, không tải trọng số, không tạo GPU job. Khi kiểm tra thật cần có ComfyUI cài riêng tại loopback, model/VRAM được xác minh, bằng chứng clip MP4 có frame motion thực, continuity và Owner playback. Tham khảo [runtime checklist](verification/runtime_2026_11/README.md), [motion pilot](architecture/FILM_MOTION_12GB_PILOT.md) và [Owner production gate](verification/OWNER_PRODUCTION_GATE.md).

## Ranh giới không được vi phạm

- `data/`, `workspace/`, `.env`, model checkpoints và backup thuộc Owner: **không xóa, không tự động migrate hay ghi đè**.
- Film, Character Registry và Publishing chỉ chạy theo manifest/Owner approvals; không suy diễn publish thành công từ FFmpeg QA.
- Hạ tầng media/image/FFmpeg có thể dùng chung; các sản phẩm cũ đã nghỉ không được mở lại qua alias/CLI chỉ để giữ tính tương thích.
- Khi gặp task archived, giữ khả năng đọc lịch sử nhưng không tự cấp quyền chạy lại kỹ năng đã nghỉ.

Xem [cấu trúc](architecture/REPOSITORY_STRUCTURE.md), [trạng thái](STATUS.md), [Đợt 1](audits/PHASE1_ACCEPTANCE.md) và [Đợt 2](audits/PHASE2_BACKEND_ACCEPTANCE.md).
