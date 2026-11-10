# File Catalog — danh mục file AgentForge hiện tại

**Source baseline:** sau M8 + M4a–M4d2 (09/11/2026). **204 file Python** (M0–M3 + Model Hub + M8 + M4a + M4b + M4c + M4d1 + M4d2); Dashboard đã có Model Hub tại `#/models`. M4a Growth, M4b Websites, M4c Webapps, M4d1 Media/Film Studio đã chuyển sang `features/`. M5 phase 1 đã chuyển 22 root compatibility aliases trỏ thẳng `features/` nhưng chưa xóa alias. Các mô tả bên dưới là module hiện có, không phải lời hứa về feature tương lai.

- [Cấu trúc đã được chốt](TARGET_STRUCTURE.md) — `agentforge/` và `dashboard/` ngay root, feature-first.
- [Kế hoạch chuyển](MIGRATION_PLAN.md) — không phá paths/import/SQLite.
- [Cấu trúc source đang chạy](REPOSITORY_STRUCTURE.md) — `agentforge/`, `dashboard/`.

## Phân loại

| Nhãn | Ý nghĩa |
| --- | --- |
| **ENTRY/API** | Entrypoint hoặc transport trực tiếp; cần giữ contract khi tách file. |
| **COMPAT** | Alias/facade/wrapper sang module khác; **không mặc nhiên là duplicate thừa**. |
| **LOGIC/CORE/AI/OPS** | Có implementation, store, adapter, orchestration hoặc policy thật. |
| **CLI** | Công cụ vận hành/demo theo lệnh, cần xem callers trước khi bỏ. |
| **CONTRACT** | Module mô tả/kiểm tra hợp đồng cấu trúc, không tự chạy workflow. |

**Tổng cộng: 204 file `.py`** (137 baseline + 15 M3 + 2 M6 + 6 M8 adapters + 5 M4a + 13 M4b + 9 M4c + 8 M4d1 + 2 M4d2 + 2 M9 ops modules + 1 Wave 5 acceptance module + 1 Wave 6 source revision module + 2 Wave 7 QA/export modules + 1 Wave 8 Film runtime module). Package marker `__init__.py` vẫn được tính. Các mô tả ngắn không thay thế docstring và tests của từng module.

## **Entrypoints và modules tại package root**

| File hiện tại dưới `agentforge/` | Loại | Vai trò |
| --- | --- | --- |
| `__init__.py` | ENTRY | Dấu mốc package Python, không chứa business logic. |
| `__main__.py` | ENTRY | Khởi chạy server Owner Dashboard bằng python -m agentforge. |
| `analytics_insights.py` | LOGIC | Tính metrics/insights theo dữ liệu analytics đã ghi; nhãn synthetic và verified khác nhau. |
| `analytics_pipeline.py` | CLI | Nhập CSV, tạo dataset demo và điều phối báo cáo S3. |
| `analytics_store.py` | LOGIC | SQLite import/store dữ liệu analytics theo SHA và các khóa chống ghi trùng. |
| `architecture.py` | CONTRACT | Snapshot đọc-only về đường dẫn, domain và danh sách compatibility aliases. |
| `artifact_catalog.py` | COMPAT | Wrapper sang storage/artifact_catalog.py để đọc danh mục artifact. |
| `asset_preview.py` | LOGIC | Đọc ảnh AI đã nhập, kiểm tra SHA và quyền truy cập. |
| `autopilot_v13.py` | LOGIC | Hàng đợi draft có ủy quyền giới hạn; không tự cấp quyền mới hay retry. |
| `brain_planner.py` | COMPAT | Alias sang core/brain_planner.py; giữ import/CLI cũ. |
| `brain_runner.py` | COMPAT | Alias sang core/brain_runner.py; giữ module identity cho tests. |
| `brain_scheduler.py` | LOGIC | Lịch thực thi theo tick có kiểm soát và slot chống lặp. |
| `brain_store.py` | COMPAT | Alias sang core/brain_store.py; tương thích SQLite paths. |
| `browser_fix.py` | LOGIC | Đề xuất sửa website từ browser QA report; không tự apply. |
| `browser_validation.py` | COMPAT | Alias sang features/websites/browser_validation.py. |
| `company_brain.py` | CLI | CLI cho lập kế hoạch Goal, phê duyệt và chạy Company Brain. |
| `company_flow.py` | CLI | Bàn giao research report thành task review thủ công. |
| `company_v2.py` | CLI | Tổng hợp scorecard vận hành; không chứng minh lợi nhuận. |
| `competitor_facts.py` | LOGIC | Trích xuất trường thông tin đối thủ từ nguồn báo cáo. |
| `competitors.py` | LOGIC | Danh sách nguồn đối thủ và thu thập thông tin đối chiếu. |
| `control_center_v1.py` | COMPAT | Facade giữ `create_server`, `_owner_action` và CLI cũ; API runtime thực ở `api/server.py`. |
| `customer_evidence_review.py` | LOGIC | Owner review ghi chú phỏng vấn khách hàng (không xác minh danh tính). |
| `customer_problem_evidence.py` | LOGIC | Đăng ký các bằng chứng vấn đề khách hàng đã được Owner xác nhận. |
| `customer_validation.py` | LOGIC | Nhập dữ liệu phỏng vấn khách hàng local. |
| `evaluation.py` | LOGIC | Đánh giá mức độ sẵn sàng cơ hội từ bằng chứng. |
| `evidence.py` | LOGIC | Tạo/chuẩn hóa claim evidence từ research. |
| `evidence_registration.py` | LOGIC | Ghi đăng ký evidence có provenance sau review. |
| `evidence_registry.py` | LOGIC | Kiểm tra references trong index evidence local. |
| `gateway.py` | LOGIC | Gateway file path/write an toàn dưới workspace. |
| `goal_preflight.py` | LOGIC | Kiểm tra entity tham chiếu trước khi duyệt Goal; read-only. |
| `growth_bundle.py` | COMPAT | Alias sang features/growth/bundle.py. |
| `growth_pipeline.py` | CLI | CLI growth offline, report/reconcile và handoff. |
| `growth_reports.py` | COMPAT | Alias sang features/growth/reports.py. |
| `growth_store.py` | COMPAT | Alias sang features/growth/store.py. |
| `image_studio_v24.py` | COMPAT | Alias sang features/websites/image_studio.py. |
| `media_assets.py` | COMPAT | Alias sang features/media/assets.py. |
| `media_pipeline.py` | CLI | CLI orchestrate S2 media demo và skill adapters. |
| `media_quality.py` | COMPAT | Alias sang features/media/quality.py. |
| `media_render.py` | COMPAT | Alias sang features/media/render.py. |
| `media_workflow_v15.py` | COMPAT | Alias sang features/media/workflow.py. |
| `model.py` | AI | Gọi model qua provider Ollama/Anthropic; guard token/budget. |
| `model_health.py` | COMPAT | Wrapper sang ai/model_health.py. |
| `model_registry.py` | COMPAT | Wrapper sang ai/model_registry.py. |
| `ops_backup.py` | OPS | Backup SQLite, xác minh ZIP/SHA và staged restore không ghi đè. |
| `ops_control.py` | OPS | Owner pause/resume các dispatch mới, fail-closed khi hỏng trạng thái. |
| `ops_daemon.py` | OPS | Foreground scheduler daemon có advisory lock và heartbeat. |
| `ops_doctor.py` | OPS | Chẩn đoán read-only, trạng thái DB/task/scheduler/backup. |
| `owner_review.py` | LOGIC | Owner review các candidates evidence; không tự đăng ký evidence. |
| `pain_discovery.py` | LOGIC | Khám phá pain points từ tìm kiếm community, lưu đầu mối. |
| `paths.py` | CORE | Định nghĩa repository root, data/workspace/UI paths và path guards. |
| `product_builder.py` | COMPAT | Alias sang features/websites/builder.py, giữ CLI/import. |
| `product_cycle.py` | LOGIC | Build → browser check → fix-proposal loop có checkpoint. |
| `product_quality.py` | COMPAT | Alias sang features/websites/quality.py. |
| `product_revision.py` | COMPAT | Alias sang features/websites/revision.py. |
| `prompt_intake.py` | COMPAT | Wrapper sang ai/prompt_intake.py. |
| `quality_v14.py` | LOGIC | Business profile, conservative QA và Owner review inbox. |
| `research.py` | CLI | Research LangGraph, checkpoints và local reports. |
| `result_view.py` | COMPAT | Wrapper sang core/result_view.py. |
| `review_handoff.py` | LOGIC | Chuyển observations thành Owner review candidates. |
| `search_quality.py` | LOGIC | Lọc chất lượng search/community hits. |
| `skill_registry.py` | COMPAT | Alias sang core/skill_registry.py. |
| `skill_runner.py` | COMPAT | Alias sang core/skill_runner.py. |
| `source_reader.py` | LOGIC | Đọc web nguồn allowlisted, có giới hạn host/nội dung. |
| `source_review.py` | LOGIC | Review trích dẫn nguồn theo task, có owner consent. |
| `task_history.py` | COMPAT | Alias sang core/task_history.py. |
| `task_inbox.py` | LOGIC | Task inbox cho review thủ công, chỉ quản lý metadata. |
| `tool_flow.py` | CLI | LangGraph flow demo write/read tool qua gateway. |
| `web_assets.py` | COMPAT | Alias sang features/websites/assets.py. |
| `web_design_kit.py` | COMPAT | Alias sang features/websites/design_kit.py. |
| `web_design_v2.py` | CLI | Điều phối revision website theo design kit và QA. |
| `web_tools.py` | LOGIC | Web search adapter DDGS, lọc response có giới hạn. |
| `webapp_architect.py` | COMPAT | Facade sang features/webapps/architect.py. |
| `webapp_builder.py` | COMPAT | Alias sang features/webapps/builder.py. |
| `webapp_developer.py` | COMPAT | Alias CLI sang features/webapps/developer.py. |
| `webapp_feedback.py` | LOGIC | Mở Goal revision cho app template theo Owner feedback. |
| `webapp_reviewer.py` | COMPAT | Facade sang features/webapps/reviewer.py. |
| `webapp_sandbox.py` | COMPAT | Alias CLI sang features/webapps/sandbox.py. |
| `webapp_static_qa.py` | COMPAT | Facade sang features/webapps/static_qa.py. |
| `website_feedback.py` | COMPAT | Facade sang features/websites/feedback.py. |
| `website_preview.py` | COMPAT | Facade sang features/websites/preview.py. |
| `worker_registry.py` | COMPAT | Wrapper sang ai/worker_registry.py. |
| `workflow.py` | CLI | LangGraph workflow sample/checkpoint cũ, không phải dashboard entrypoint. |
| `workflow_runner.py` | LOGIC | S1 bounded website quality/browser workflow với checkpoint. |
| `workspace_policy.py` | LOGIC | SQLite quota/limits cho prompt-first workspace. |

## **API: `api/` (M3 hoàn thành)**

| File dưới `agentforge/` | Vai trò |
| --- | --- |
| `api/__init__.py` | Package marker for modular HTTP API. |
| `api/auth.py` | Owner one-time login, session, CSRF cookie lifecycle; no durable credentials. |
| `api/server.py` | Canonical HTTP transport: localhost bind, Host/Origin/CSRF, JSON, CSP, read/write dispatch. |
| `api/static.py` | Only serves allowlisted trusted React build assets from dashboard/dist. |
| `api/routes/__init__.py` | Package marker for bounded route handlers. |
| `api/routes/_shared.py` | Identity sentinel distinguishing an unhandled route from a valid None result. |
| `api/routes/bootstrap.py` | Read-only aggregates, Owner attention, task/public artifact presentation. |
| `api/routes/read.py` | Authenticated GET endpoints, preserving 404 and review session markers. |
| `api/routes/mutations.py` | Small static allowlisted dispatcher; never executes arbitrary model-supplied paths. |
| `api/routes/artifacts.py` | SHA-bound artifact acceptance and reversible retention actions. |
| `api/routes/media.py` | Explicit image generation/import, storyboard/video and draft decisions. |
| `api/routes/workspace.py` | Workspace prompt/policy and bounded Autopilot configuration. |
| `api/routes/operations.py` | Explicit Owner pause/resume operations. |
| `api/routes/products.py` | Signed Website/WebApp inspect/revise/apply action guards. |
| `api/routes/goals.py` | Goal approval/execution, schedules, campaigns and Owner memory actions. |
| `api/routes/model_hub.py` | GET/POST Owner Model Hub, CAS revision, local model metadata probe có xác nhận. |

## **AI: `ai/`**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `ai/__init__.py` | Package AI. |
| `ai/model_health.py` | Đọc read-only trạng thái Ollama; không gọi generation. |
| `ai/model_hub.py` | Model profiles, task route capabilities, SQLite Owner overrides, rollback và cloud consent boundaries. |
| `ai/model_registry.py` | Load model profiles từ models.toml, không chứa credentials. |
| `ai/prompt_intake.py` | Định tuyến natural language request vào template allowlisted. |
| `ai/role_routing.py` | Định tuyến worker-to-model có cấu hình được duyệt. |
| `ai/worker_registry.py` | Đọc và validate worker manifests. |

## **Core: `core/`**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `core/__init__.py` | Package lõi. |
| `core/artifact_acceptance.py` | Artifact status, evidence SHA và Owner acceptance ledger. |
| `core/brain_planner.py` | Đề xuất plans theo Goal templates có giới hạn. |
| `core/brain_runner.py` | Điều phối thực thi từng step, durable dispatch/no-blind-retry. |
| `core/brain_store.py` | SQLite Goal/plan/step state và audit. |
| `core/public_serialization.py` | Projection metadata public không lộ prompt/absolute paths. |
| `core/result_view.py` | Allowlisted read-only presentation của task results. |
| `core/skill_registry.py` | Đọc skill contracts TOML và kiểm tra schema. |
| `core/skill_runner.py` | Permission checks, task persistence và gọi trusted domain adapters. |
| `core/skill_adapters/__init__.py` | Allowlisted domain adapter map, fail closed với unknown skill. |
| `core/skill_adapters/web.py` | Policy + handlers cho website và React webapp. |
| `core/skill_adapters/research.py` | Policy + handlers cho research, capture stdout. |
| `core/skill_adapters/media.py` | Policy + handlers cho media với external-run approvals. |
| `core/skill_adapters/analytics.py` | Policy + handlers cho import/report analytics. |
| `core/skill_adapters/growth.py` | Policy + handlers cho campaign/growth handoff. |
| `core/task_history.py` | Lịch sử task/events SQLite và recovery. |

## **Feature-first: `features/growth/` (M4a)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `features/__init__.py` | Package cho business features. |
| `features/growth/__init__.py` | Package business Growth. |
| `features/growth/store.py` | Canonical SQLite campaign/lead/finance, giữ data path cũ. |
| `features/growth/reports.py` | Canonical read-only growth reports. |
| `features/growth/bundle.py` | Canonical manual-owner publishing handoffs. |

## **Domains: `domains/growth/` (COMPAT)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `domains/growth/__init__.py` | Package nghiệp vụ growth. |
| `domains/growth/bundle.py` | COMPAT alias tới `features/growth/bundle.py`. |
| `domains/growth/reports.py` | COMPAT alias tới `features/growth/reports.py`. |
| `domains/growth/store.py` | COMPAT alias tới `features/growth/store.py`. |

## **Feature-first: `features/media/` + `features/film_studio/` (M4d1)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `features/media/__init__.py` | Package shared media feature. |
| `features/film_studio/__init__.py` | Package phim AI planning, Owner-gated motion. |
| `features/media/assets.py` | Canonical `media` implementation cho `assets`. |
| `features/media/quality.py` | Canonical `media` implementation cho `quality`. |
| `features/media/render.py` | Canonical `media` implementation cho `render`. |
| `features/media/workflow.py` | Canonical `media` implementation cho `workflow`. |
| `features/film_studio/long_form.py` | Canonical `film_studio` implementation cho `long_form`. |
| `features/film_studio/motion_verify.py` | Wave 8 Comfy local MP4 intake, ffprobe/FFmpeg verification and immutable SHA receipt. |
| `features/film_studio/motion_comfy.py` | Canonical `film_studio` implementation cho `motion_comfy`. |

## **Domains: `domains/media/` (COMPAT)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `domains/media/__init__.py` | Package media hiện tại. |
| `domains/media/assets.py` | COMPAT alias tới `features/media/assets.py`. |
| `domains/media/long_form.py` | COMPAT alias tới `features/film_studio/long_form.py`. |
| `domains/media/motion_comfy.py` | COMPAT alias tới `features/film_studio/motion_comfy.py`. |
| `domains/media/quality.py` | COMPAT alias tới `features/media/quality.py`. |
| `domains/media/render.py` | COMPAT alias tới `features/media/render.py`. |
| `domains/media/workflow.py` | COMPAT alias tới `features/media/workflow.py`. |

## **Feature-first: `features/webapps/` (M4c)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `features/webapps/__init__.py` | Canonical Webapp feature package. |
| `features/webapps/architect.py` | Canonical implementation `architect`. |
| `features/webapps/builder.py` | Canonical implementation `builder`. |
| `features/webapps/browser_qa.py` | Owner-gated local offline Chromium QA and screenshot SHA reports. |
| `features/webapps/exporter.py` | Deterministic source ZIP, per-file integrity manifest and source SHA. |
| `features/webapps/revisions.py` | Wave 6 source-aware React edit, immutable lineage, bounded diff and ancestor rollback. |
| `features/webapps/developer.py` | Canonical implementation `developer`. |
| `features/webapps/reviewer.py` | Canonical implementation `reviewer`. |
| `features/webapps/sandbox.py` | Canonical implementation `sandbox`. |
| `features/webapps/static_qa.py` | Canonical implementation `static_qa`. |
| `features/webapps/syntax.py` | Canonical implementation `syntax`. |
| `features/webapps/toolchain.py` | Canonical implementation `toolchain`. |

## **Domains: `domains/webapps/` (COMPAT)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `domains/webapps/__init__.py` | Package React WebApp. |
| `domains/webapps/architect.py` | COMPAT alias tới `features/webapps/architect.py`. |
| `domains/webapps/builder.py` | COMPAT alias tới `features/webapps/builder.py`. |
| `domains/webapps/developer.py` | COMPAT alias tới `features/webapps/developer.py`. |
| `domains/webapps/reviewer.py` | COMPAT alias tới `features/webapps/reviewer.py`. |
| `domains/webapps/sandbox.py` | COMPAT alias tới `features/webapps/sandbox.py`. |
| `domains/webapps/static_qa.py` | COMPAT alias tới `features/webapps/static_qa.py`. |
| `domains/webapps/syntax.py` | COMPAT alias tới `features/webapps/syntax.py`. |
| `domains/webapps/toolchain.py` | COMPAT alias tới `features/webapps/toolchain.py`. |

## **Feature-first: `features/websites/` (M4b)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `features/websites/__init__.py` | Package Canonical Website. |
| `features/websites/ai_designer.py` | Canonical implementation cho `ai_designer`. |
| `features/websites/assets.py` | Canonical implementation cho `assets`. |
| `features/websites/browser_validation.py` | Canonical implementation cho `browser_validation`. |
| `features/websites/builder.py` | Canonical implementation cho `builder`. |
| `features/websites/design_kit.py` | Canonical implementation cho `design_kit`. |
| `features/websites/feedback.py` | Canonical implementation cho `feedback`. |
| `features/websites/image_studio.py` | Canonical implementation cho `image_studio`. |
| `features/websites/preview.py` | Canonical implementation cho `preview`. |
| `features/websites/quality.py` | Canonical implementation cho `quality`. |
| `features/websites/revision.py` | Canonical implementation cho `revision`. |
| `features/websites/revision_context.py` | Canonical implementation cho `revision_context`. |
| `features/websites/structured_builder.py` | Canonical implementation cho `structured_builder`. |

## **Domains: `domains/websites/` (COMPAT)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `domains/websites/__init__.py` | Package Website. |
| `domains/websites/ai_designer.py` | COMPAT alias tới `features/websites/ai_designer.py`. |
| `domains/websites/assets.py` | COMPAT alias tới `features/websites/assets.py`. |
| `domains/websites/browser_validation.py` | COMPAT alias tới `features/websites/browser_validation.py`. |
| `domains/websites/builder.py` | COMPAT alias tới `features/websites/builder.py`. |
| `domains/websites/design_kit.py` | COMPAT alias tới `features/websites/design_kit.py`. |
| `domains/websites/feedback.py` | COMPAT alias tới `features/websites/feedback.py`. |
| `domains/websites/image_studio.py` | COMPAT alias tới `features/websites/image_studio.py`. |
| `domains/websites/preview.py` | COMPAT alias tới `features/websites/preview.py`. |
| `domains/websites/quality.py` | COMPAT alias tới `features/websites/quality.py`. |
| `domains/websites/revision.py` | COMPAT alias tới `features/websites/revision.py`. |
| `domains/websites/revision_context.py` | COMPAT alias tới `features/websites/revision_context.py`. |
| `domains/websites/structured_builder.py` | COMPAT alias tới `features/websites/structured_builder.py`. |

## **Operations: `ops/` (M9)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `ops/__init__.py` | Package operational helpers. |
| `ops/preflight.py` | Read-only local environment preflight; no subprocess/network/model invocation. |
| `ops/base_acceptance.py` | Wave 5 status gate: setup/health/model routing summary, Owner acceptance always UNVERIFIED until independently checked. |

## **Integrations: `integrations/` (M4d2)**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `integrations/__init__.py` | Package HTTP/local provider adapters; không quyết định Owner approval. |
| `integrations/comfyui.py` | Bounded localhost ComfyUI JSON transport; no proxy, no redirects, no retry. |

## **Storage: `storage/` và package marker**

| File hiện tại dưới `agentforge/` | Vai trò |
| --- | --- |
| `domains/__init__.py` | Package compatibility cho các domain đã migrate và implementation còn lại. |
| `storage/__init__.py` | Package storage. |
| `storage/artifact_catalog.py` | Read-only artifact inventory, không xóa/chạy source. |
| `storage/retention.py` | Backup/retention, reversible quarantine và restore không ghi đè. |

## Frontend React hiện tại (`dashboard/` tại root, M1 đã chuyển)

| File/nhóm | Vai trò |
| --- | --- |
| `index.html`, `src/main.jsx` | HTML shell và React entrypoint. |
| `src/App.jsx` | App shell, login/Owner controls và navigation layout. |
| `src/api.js` | HTTP/session/CSRF frontend client. |
| `src/navigation.js` | Định nghĩa tabs/route mapping. |
| `src/model_hub_ui.js` | Helpers capability filtering và presentation; quyền được backend kiểm soát. |
| `src/permissions.js` | Presentation/permission checks trong UI; backend vẫn là authority. |
| `src/acceptance.js` | Projection/labels cho artifact acceptance states. |
| `src/workspace_quota.js` | Ước lượng/presentation quota workspace. |
| `src/styles.css` | Global CSS, responsive layout và dark theme. |
| `src/theme.jsx` | Theme/token config React/Ant Design. |
| `src/components/AcceptanceStatus.jsx` | Hiển thị trạng thái nghiệm thu. |
| `src/components/shared.jsx` | UI primitives dùng lại. |
| `src/features/Management.jsx` | Màn hình quản lý hệ thống. |
| `src/features/Models.jsx` | AI Models & Routing: chỉnh profile, gán route, health metadata, rollback. |
| `src/features/Operations.jsx` | Màn hình Operations. |
| `src/features/Projects.jsx` | Màn hình Projects. |
| `src/features/Retention.jsx` | Màn hình backup/retention. |
| `src/features/Reviews.jsx` | Màn hình Owner reviews. |
| `src/features/Webapps.jsx` | Màn hình WebApp/React proposals. |
| `src/features/Websites.jsx` | Màn hình Website Builder. |
| `src/features/Workspace.jsx` | Màn hình giao việc/workspace. |
| `tests/acceptance.test.js` | Regression UI acceptance. |
| `tests/navigation.test.js` | Regression navigation. |
| `tests/models.test.js` | Regression route compatibility, cloud/media warnings, payload validation UI. |
| `tests/permissions.test.js` | Regression visibility/permission UI. |
| `tests/workspace-quota.test.js` | Regression quota UX. |
| `tests/browser-smoke.mjs` | Smoke browser trên trusted dashboard build. |
| `vite.config.js` | Vite root/base/build config. |
| `package.json`, `package-lock.json` | Scripts, dependencies và lockfile npm; không xóa lockfile. |
| `README.md` | Tài liệu module frontend hiện hành. |

## Các file ở repository root và scripts

| File/nhóm | Vai trò |
| --- | --- |
| `README.md` | Giới thiệu, setup nhanh và link tài liệu hiện hành. |
| `pyproject.toml` | Python packaging flat-root: `where=["."]`, chỉ include `agentforge` và `agentforge.*`. |
| `.gitignore` | Bỏ qua dữ liệu runtime, venv, npm dependencies/build output. |
| `.env.example` | Ví dụ biến môi trường; không commit `.env` thật. |
| `.github/workflows/ci.yml` | Windows Python/Node/Edge CI và docs lint. |
| `config/` | Model/Owner config đã review; không chứa token bí mật. |
| `skills/` | Skill manifests và policy contracts. |
| `workers/` | Worker TOML và instructions; không tự chạy code. |
| `templates/novamart/` | Trusted React marketplace scaffold và integration test fixture: nguồn bắt buộc cho WebApp Builder; giữ lockfile. |
| `examples/` | JSON minh họa, gồm film_studio/feature_fantasy.json và nem-ngu-storyboard-v15.json; không phải source generator. |
| `sandbox/webapp/` | Docker QA specification/instructions, thực runtime còn phải kiểm chứng. |
| `scripts/agentforge_acceptance_windows.ps1` | Read-only PowerShell acceptance smoke. |
| `scripts/archive_local_state.py` | Công cụ archive local state theo quy tắc an toàn. |
| `scripts/check_docs.py` | Kiểm tra Markdown relative links, chạy trong CI. |
| `scripts/repo_hygiene.py` | Báo cáo/dọn cache bytecode có xác nhận, không xóa Owner data. |
| `scripts/s2_tts_windows.ps1` | Thiết lập/kiểm tra TTS Windows cho media. |
| `tests/` | Regression Python, browser/Node reference tests và security constraints. |
| `data/`, `workspace/` | Owner SQLite/proposals/films; gitignored, **không bao giờ cleanup tự động**. |

## Nguyên tắc cập nhật catalog

Mỗi lần migration thực sự được merge, cập nhật đường dẫn trong catalog hoặc chuyển tài liệu này thành **migration baseline snapshot** và tạo catalog mới từ HEAD. Không gọi một tên file đã bỏ là active; không xóa một alias chỉ vì rất ngắn. Với mọi file chưa xác minh callers, giữ file và đánh dấu cần audit thay vì tự kết luận UNUSED.
