# Kiến trúc repository AgentForge

> **CURRENT IMPLEMENTATION** — M1/M2 đặt Python `agentforge/` và React `dashboard/` tại root; **M3 đã tách API thành `agentforge/api/`**. M4/M5 chuyển features/integrations/compatibility aliases **chưa thực hiện**. Xem [catalog từng file](FILE_CATALOG.md) và [kế hoạch migration](MIGRATION_PLAN.md).

**Current source of truth:** Python modular monolith, một React dashboard, local SQLite + workspace. Đã loại bỏ frontend HTML/CSS/JS V0 và Python dashboard V0.

## Cấu trúc đang sử dụng

~~~text
AgentForge/
├── agentforge/
│   ├── __main__.py                 # python -m agentforge
│   ├── control_center_v1.py       # Compatibility facade cho import/CLI cũ
│   ├── api/                       # Canonical localhost HTTP, auth, static, routes
│   │   ├── server.py              # HTTP transport, CSP, CSRF, request parsing
│   │   ├── auth.py                # Owner sessions/login
│   │   ├── static.py              # Strictly trusted React assets
│   │   └── routes/                # Bootstrap, GET and domain-specific mutations
│   ├── ai/                        # AI intake, routing, provider profiles
│   ├── core/                      # workflow, tasks, permissions, artifact acceptance
│   ├── domains/
│   │   ├── websites/              # website proposals, design JSON, revision
│   │   ├── webapps/               # NovaMart, React Developer, static QA, sandbox adapter
│   │   ├── media/                 # image/SRT/FFmpeg + film planner/motion ComfyUI
│   │   └── growth/                # demo campaigns, offline handoff
│   ├── storage/                   # storage and retention logic
│   └── paths.py                   # local root and path guards
├── dashboard/                     # ONLY Owner frontend (React + Vite)
├── templates/novamart/            # trusted React marketplace runtime template
├── examples/                      # sample film/storyboard JSON only
├── skills/                        # skill contracts, tool permissions
├── workers/                       # worker manifests and instructions
├── config/                        # model configuration templates
├── scripts/                       # maintenance and safety checks
├── tests/                         # Python and Node regression
├── docs/                          # current, evidence, historic docs
├── data/                          # Owner SQLite/ledgers (gitignored)
└── workspace/                     # Owner products/films/proposals (gitignored)
~~~

`agentforge/` là **backend Python đang chạy** ở root, còn `dashboard/` là frontend React; URL vẫn `/dashboard/`. Namespace Python `agentforge.*`, các CLI và SQLite paths không đổi về ý nghĩa. M3 đã hoàn thành trong scope API; M4/M5 là các đợt refactor domain và aliases còn lại. Những Python compatibility aliases root-level được giữ nếu còn CLI, imports hoặc tests phụ thuộc. Không tự tái tổ chức tất cả folder chỉ để đẹp cây thư mục.

## Vòng đời sản phẩm

1. Owner đưa brief → `ai/prompt_intake.py` route vào allowlisted goal/skill.
2. Workflow và worker tạo proposal; input/output được bảo vệ bằng permission + budget.
3. Source/design/artifact được lưu với SHA; QA evidence có phạm vi rõ.
4. Owner inspect, feedback/approve/decision; không tự ACCEPTED khi thiếu gate.
5. Local deliverable nằm trong `workspace/`; không có implicit deploy/upload.

Với Film Studio: `domains/media/long_form.py` chỉ tạo shot slots; `motion_comfy.py` chỉ gửi job ComfyUI theo quyền Owner. ComfyUI `history.success` **không phải** QA đạt hoặc video đã hoàn thành.

## Ranh giới vận hành

- HTTP bind **localhost**, không public; dữ liệu Owner không dùng chung với người khác.
- Generated JavaScript không chạy trên host Windows khi thiếu sandbox tin cậy.
- Các subprocess media chỉ chạy theo lệnh và quyền rõ ràng, model phải do Owner cài đặt.
- Local ComfyUI `127.0.0.1:8188` không được tự suy ra đang khả dụng.
- Không mở rộng khả năng của module bằng cách xóa guard, bypass acceptance hay tự cho PASS.

## Những đường dẫn được bảo vệ

`data/`, `workspace/`, `.env`, model weights, backup và video/proposal do Owner tạo **không thuộc cleanup Git**. Không xóa hoặc overwrite tự động. Cần backup, SHA/integrity và thao tác cụ thể do Owner cho phép.

## Tài liệu liên quan

- [Tổng quan trạng thái](../STATUS.md)
- [Roadmap](../ROADMAP.md)
- [Cài đặt và kiểm thử](../DEVELOPMENT.md)
- [Long-form Film Studio](LONG_FORM_AI_FILM_STUDIO.md)
- [GPU 12 GB pilot](FILM_MOTION_12GB_PILOT.md)
