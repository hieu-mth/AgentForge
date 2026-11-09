# AgentForge — Ngữ cảnh chuẩn của dự án

> **Cập nhật:** 09/11/2026. Dùng để tiếp tục trao đổi kỹ thuật trong chat mới. Đây là mô tả mục tiêu và source tại thời điểm ghi; **không thay thế việc kiểm tra HEAD, CI hoặc code thật**.

## 1. Tầm nhìn và cách làm việc

AgentForge là **local-first AI Product Studio**, không phải bản SaaS đã hoàn thiện. Trách nhiệm của technical cofounder: ưu tiên giá trị kinh doanh, kiểm tra bằng chứng, tránh over-engineering, giữ kiến trúc module dễ thay đổi model/tool. Có thể refactor và merge `main` sau khi tests/CI PASS theo yêu cầu Owner; không tự xóa dữ liệu, public sản phẩm hay gọi API trả phí.

Bối cảnh vận hành: Windows PowerShell, Python >=3.13, Node.js 22, React Dashboard, một Owner; máy phát triển có **12 GB VRAM theo thông tin Owner**, chưa có kết quả benchmarking AI video trên GPU đó. Owner ưu tiên **chưa dùng Docker** cho phát triển bình thường, nhưng không cho phép thực thi source AI chưa đáng tin cậy trên host.

## 2. Những gì đã triển khai

- Python backend `src/agentforge/`, domain/core/storage/ai; task/goal, SQLite, skill permissions, owner approvals.
- Dashboard chính: `ui/dashboard/` (React). `python -m agentforge --port 8780` chạy server; `/` redirect tới `/dashboard/`.
- Website Builder dạng structured design + signed `site.json`, feedback chỉnh thiết kế; Marketplace NovaMart demo (không có checkout thật).
- Experimental AI React Developer tạo đề xuất JSX/CSS; syntax validation và acceptance SHA, **chưa source revision**.
- Phase 1: tách execution status / artifact acceptance; verify source SHA, static syntax, CI build trusted reference. Chưa có browser QA/source isolation thực cho React AI.
- Media S2: storyboard, assets ảnh tĩnh, SRT, TTS tùy chọn, FFmpeg MP4, review. Không tự đăng YouTube.
- Film Studio: long-form planner phân chapter/cast/shot, adapter ComfyUI một shot 4 giây ở 640×352, 49 frames, 12 fps, batch 1. **Adapter có, chưa tạo video động thành công trên GPU Owner.**

## 3. Quyết định kiến trúc

**Quyết định mới (09/11/2026):** Owner đã chốt structure đích `agentforge/` và `dashboard/` ngang cấp root, bên trong dùng `api/`, `core/`, `ai/`, `features/`, `integrations/`, `ops/`, `storage/`. Đây vẫn là **planned migration, không phải code đã chuyển**. Xem [ADR](architecture/TARGET_STRUCTURE.md), [catalog từng file](architecture/FILE_CATALOG.md) và [migration plan](architecture/MIGRATION_PLAN.md).

- Một frontend, một Python backend modular monolith. SQLite và workspace local.
- Legacy dashboard static và `dashboard_v0.py` đã bị loại bỏ. `src/agentforge/` **không phải code cũ**.
- Các compatibility Python alias chỉ xóa sau khi chứng minh không còn dependency.
- Người dùng kiểm tra source, SHA và QA evidence trước khi ACCEPTED; workflow success không đồng nghĩa artifact success.
- Không Docker vẫn được viết/test logic, nhưng không chạy source AI chưa tin cậy trên host.
- Không tự suy ra chất lượng video/model từ model docs hay mock unit tests.

## 4. Ưu tiên hiện tại

1. AI Film Studio: thực nghiệm motion 4 giây trên GPU 12 GB, sau đó clip QA → continuity → dựng phim nhiều cảnh → phim dài 1–3 giờ → đăng YouTube được Owner duyệt.
2. AI React: triển khai source revision và build/browser QA; hạn chế template hardcoded.
3. Đơn giản hóa docs, giữ test CI và các module thực sự đang chạy.

Đường dẫn nguồn: [trạng thái](STATUS.md), [roadmap](ROADMAP.md), [phát triển](DEVELOPMENT.md), [kiến trúc](architecture/REPOSITORY_STRUCTURE.md), [film 12 GB](architecture/FILM_MOTION_12GB_PILOT.md).

## 5. Các khẳng định tuyệt đối không được tự động suy diễn

- Không gọi AgentForge là hệ thống tạo phim AI chuyển động dài vài giờ đã hoàn thành.
- Không gọi model Wan 2.2 5B đã chạy ổn trên 12 GB trước khi có clip và số đo thật.
- Không coi code AI generated đã build/browser PASS khi chỉ parse cú pháp.
- Không tuyên bố có YouTube auto-upload, OAuth, doanh thu, multi-tenant hay hệ thống thanh toán.
- Không xóa `data/`, `workspace/`, `.env`, user artifacts và các lịch sử audit quan trọng.

Snapshot Master Context trước đây (04/11/2026) có thể xem trong [Git history](archive/README.md) nhưng không còn dùng làm hướng dẫn triển khai hiện hành.
