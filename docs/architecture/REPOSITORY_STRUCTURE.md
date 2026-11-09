# Kiến trúc repository AgentForge

**Current source of truth:** Python modular monolith, một React dashboard, local SQLite + workspace. Đã loại bỏ frontend HTML/CSS/JS V0 và Python dashboard V0.

## Cấu trúc đang sử dụng

~~~text
AgentForge/
├── src/agentforge/
│   ├── __main__.py                 # python -m agentforge
│   ├── control_center_v1.py       # Owner HTTP, session/CSRF, JSON API, React dist
│   ├── ai/                        # AI intake, routing, provider profiles
│   ├── core/                      # workflow, tasks, permissions, artifact acceptance
│   ├── domains/
│   │   ├── websites/              # website proposals, design JSON, revision
│   │   ├── webapps/               # NovaMart, React Developer, static QA, sandbox adapter
│   │   ├── media/                 # image/SRT/FFmpeg + film planner/motion ComfyUI
│   │   └── growth/                # demo campaigns, offline handoff
│   ├── storage/                   # storage and retention logic
│   └── paths.py                   # local root and path guards
├── ui/dashboard/                  # ONLY Owner frontend (React + Vite)
├── examples/novamart/             # trusted marketplace demo/template
├── skills/                        # skill contracts, tool permissions
├── workers/                       # worker manifests and instructions
├── config/                        # model configuration templates
├── scripts/                       # maintenance and safety checks
├── tests/                         # Python and Node regression
├── docs/                          # current, evidence, historic docs
├── data/                          # Owner SQLite/ledgers (gitignored)
└── workspace/                     # Owner products/films/proposals (gitignored)
~~~

`src/agentforge/` là **backend đang chạy**, không phải một thư mục src legacy. Những Python compatibility aliases root-level được giữ nếu còn CLI, imports hoặc tests phụ thuộc. Không tự tái tổ chức tất cả folder chỉ để đẹp cây thư mục.

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
