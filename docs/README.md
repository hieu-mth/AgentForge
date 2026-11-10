# Tài liệu AgentForge

> **Nguồn thông tin hiện hành** · Cập nhật 09/11/2026 · Local-first, Windows, một Owner.

Không sử dụng các tài liệu milestone phiên bản cũ để suy luận rằng tính năng vẫn tồn tại hoặc đã production-ready. **Source code, tests và evidence mới nhất** được ưu tiên hơn nội dung tài liệu lịch sử.

## Đọc theo nhu cầu

| Bạn cần | Tài liệu | Nội dung |
| --- | --- | --- |
| Khởi chạy | [README tại root](../README.md) | Giới thiệu, lệnh chạy nhanh |
| Xem hệ thống làm được gì | [STATUS.md](STATUS.md) | Matrix VERIFIED / PARTIAL / NOT IMPLEMENTED / UNVERIFIED |
| Film Studio runtime (Đợt 8) | [Wave 8 acceptance](verification/wave8/README.md) | Wan 5B, MP4 SHA/decode/receipt; GPU Owner pending |
| Product QA/ZIP export (Đợt 7) | [Wave 7 acceptance](verification/wave7/README.md) | Offline Chromium smoke + screenshot SHA; source ZIP manifest; Owner PC pending |
| AI React source revision (Đợt 6) | [Wave 6 acceptance](verification/wave6/README.md) | Chỉnh JSX/CSS theo feedback, SHA/diff/rollback, chưa QA model/browser thật |
| Nghiệm thu Base V1 (Đợt 5) | [Base V1 acceptance](verification/base_v1/README.md) | CI gates, workflow/backup staging, checklist Owner Windows B1–B7 |
| Cài, build, kiểm thử | [DEVELOPMENT.md](DEVELOPMENT.md) | M9 Windows preflight/setup an toàn, Python, npm, CI, kiểm tra docs |
| Quyết định phát triển | [ROADMAP.md](ROADMAP.md) | Mốc, tiêu chí nghiệm thu, blocker |
| Models & Routing Dashboard | [MODEL_HUB.md](architecture/MODEL_HUB.md) | M6/M7: providers, text runtime routing, video config-only, rollback |
| Mở rộng skill engine | [SKILL_ENGINE.md](architecture/SKILL_ENGINE.md) | M8: code policy + adapter theo domain, không cấp quyền từ manifest |
| Compatibility imports | [COMPATIBILITY_POLICY.md](architecture/COMPATIBILITY_POLICY.md) | M5: 22 root aliases direct-to-feature, audit và giới hạn cleanup |
| Feature-first module boundaries | [FEATURE_BOUNDARIES.md](architecture/FEATURE_BOUNDARIES.md) | M4: canonical features, compatibility, tích hợp ComfyUI và quy tắc thêm nghiệp vụ |
| Cấu trúc source **đang chạy** | [REPOSITORY_STRUCTURE.md](architecture/REPOSITORY_STRUCTURE.md) | `agentforge/` + `dashboard/` đang chạy |
| **Cấu trúc đã chốt (M1–M4 chính đã chuyển, M5 phase 2 còn chờ)** | [TARGET_STRUCTURE.md](architecture/TARGET_STRUCTURE.md) | `agentforge/` + `dashboard/` tại root, Feature-First Modular Monolith |
| Giải thích **từng file** | [FILE_CATALOG.md](architecture/FILE_CATALOG.md) | Catalog 201 file Python, các file React và scripts |
| Hợp đồng API đã cố định | [API_CONTRACT_V1.md](architecture/API_CONTRACT_V1.md) | Localhost/Owner/CSRF, routes và quy tắc bảo mật M0–M3 |
| Lộ trình đổi cấu trúc | [MIGRATION_PLAN.md](architecture/MIGRATION_PLAN.md) | Migration theo phase, kiểm chứng import/CLI/SQLite |
| Tạo phim dài | [LONG_FORM_AI_FILM_STUDIO.md](architecture/LONG_FORM_AI_FILM_STUDIO.md) | Chapter/shot planner, không phải video thành phẩm |
| Motion GPU 12 GB | [FILM_MOTION_12GB_PILOT.md](architecture/FILM_MOTION_12GB_PILOT.md) | ComfyUI adapter, giới hạn thực thi |
| Khôi phục ngữ cảnh dự án | [AGENTFORGE_MASTER_CONTEXT.md](AGENTFORGE_MASTER_CONTEXT.md) | Các quyết định và trạng thái cô đọng |

## Bằng chứng và lịch sử

| Nhóm | Mục đích |
| --- | --- |
| [Phase 1 verification](verification/phase1/README.md) | Báo cáo và log thời điểm 09/11; KHÔNG chứng minh Docker/GPU thật |
| [Legacy UI cleanup](verification/repository_cleanup/README.md) | Thay frontend cũ bằng React |
| [Development audit cũ](audits/DEVELOPMENT_ROADMAP.md) | Snapshot audit có đánh dấu lịch sử |
| [Milestones archive](milestones/README.md) | S1–S5, C7–C8, V2–V5: tài liệu triển khai cũ |
| [Reviews V3.x](reviews/V34_RELIABILITY_AUDIT.md) | Review theo baseline từng thời điểm |
| [Phần đã bỏ khỏi cây tài liệu](archive/README.md) | Chỉ mục lịch sử có trong Git, không làm rối docs hiện tại |

## Quy tắc cập nhật

1. **Thay đổi chức năng:** cập nhật [STATUS.md](STATUS.md) và tests cùng commit.
2. **Thay đổi định hướng:** cập nhật [ROADMAP.md](ROADMAP.md); không chỉnh sửa các snapshot audit như thể chúng là hiện tại.
3. **Thay đổi entrypoint hoặc setup:** cập nhật [DEVELOPMENT.md](DEVELOPMENT.md) và root README.
4. **Thay đổi đường dẫn:** chạy `python scripts/check_docs.py` và sửa toàn bộ link nội bộ lỗi.
5. **Viết kết quả QA:** ghi rõ cái gì thực sự chạy; không đánh đồng mocked tests với GPU inference, browser QA AI hay doanh thu.

Tài liệu ưu tiên tiếng Việt, thuật ngữ kỹ thuật và tên file/module giữ nguyên theo code.
