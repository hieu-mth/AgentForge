# AgentForge — Trạng thái thực tế

**Baseline code:** M1–M3, M6–M8 và M4a–M4d2 (09/11/2026); canonical HTTP `agentforge/api/`, business `agentforge/features/`, ComfyUI transport `agentforge/integrations/`. M6/M7 Model Hub chỉ nối text task routing; ComfyUI video/image chưa nối qua route mới.

Các nhãn được dùng thống nhất:

- **IMPLEMENTED:** code có trên repo, kiểm tra bằng test/CI tương ứng; không nhất thiết đã thử với người dùng.
- **PARTIAL:** có chức năng thật nhưng thiếu phần quan trọng hoặc chỉ chạy với template/bộ dữ liệu giới hạn.
- **UNVERIFIED:** có adapter/thiết kế nhưng chưa có bằng chứng chạy thực tế trên máy/model tương ứng.
- **NOT IMPLEMENTED:** chưa có luồng end-to-end trong repo.

## Tính năng và giới hạn

| Tính năng | Trạng thái | Bằng chứng trong source | Không được hiểu nhầm |
| --- | --- | --- | --- |
| Dashboard React + Owner session | IMPLEMENTED | `dashboard/`, `agentforge/api/server.py` | Không có multi-tenant/public hosting |
| Model Hub & Task Routing | IMPLEMENTED (text), PARTIAL (media) | `agentforge/ai/model_hub.py`, `dashboard/src/features/Models.jsx` | Text routes đã nối; video/image config-only, không chứng minh GPU hay billing |
| Task orchestration và approvals | IMPLEMENTED | `agentforge/core/`, `skills/` | Không tự động trao quyền tool cho AI |
| M5 phase 1 compatibility audit | IMPLEMENTED (không xóa alias) | `scripts/compat_audit.py`, `tests/test_m5_compatibility.py` | 22 root aliases trỏ thẳng features; external callers chưa thể xác minh |
| Wave 5 Base V1 acceptance | IMPLEMENTED (CI contract + Owner checklist) | `agentforge/ops/base_acceptance.py`, `tests/test_wave5_acceptance.py`, [acceptance guide](verification/base_v1/README.md) | Owner PC/model/artifact chưa được nghiệm thu: OWNER_PENDING |
| M9 Setup & Operations preflight | IMPLEMENTED (read-only) | `agentforge/ops/preflight.py`, `scripts/setup_windows.ps1`, Dashboard Vận hành | Không chứng minh model/GPU hoạt động, không cài dependency tự động |
| M8 skill domain adapters | IMPLEMENTED (refactor) | `agentforge/core/skill_adapters/`, `tests/test_skill_adapters_m8.py` | Không phải runtime plugin động hay quyền mở rộng từ TOML |
| M4a Growth feature-first | IMPLEMENTED (code migration) | `agentforge/features/growth/`, `tests/test_m4_growth_features.py` | Chưa tích hợp YouTube thực |
| M4b Website feature-first | IMPLEMENTED (code migration) | `agentforge/features/websites/`, `tests/test_m4_websites_features.py` | Không đồng nghĩa AI Builder đã tạo và QA website tùy ý thành công |
| M4c Webapp feature-first | IMPLEMENTED (code migration) | `agentforge/features/webapps/`, `tests/test_m4_webapps_features.py` | Generated React sandbox/browser execution vẫn chưa được kiểm chứng trên Owner PC |
| M4d1 Media/Film feature-first | IMPLEMENTED (code migration) | `agentforge/features/media/`, `agentforge/features/film_studio/` | Motion GPU thật vẫn UNVERIFIED; ComfyUI transport đã tách sang `integrations/comfyui.py` |
| Artifact acceptance gắn SHA | IMPLEMENTED | `agentforge/core/artifact_acceptance.py` | Workflow `SUCCEEDED` chưa chắc artifact `ACCEPTED` |
| Static Website Builder | PARTIAL | `agentforge/features/websites/` | Thiết kế và section bị giới hạn bởi schema; không có backend chung |
| Marketplace React demo | PARTIAL | `agentforge/features/webapps/builder.py`, `templates/novamart/` | Cart/search demo, không có checkout thanh toán |
| AI React Developer | PARTIAL | `agentforge/features/webapps/developer.py` | Danh sách file giới hạn; source là đề xuất, không tự chạy |
| Source revision cho AI React | IMPLEMENTED (code / tests) — real-model UNVERIFIED | `agentforge/features/webapps/revisions.py`, `tests/test_wave6_source_revision.py` | Partial file edits, diff/SHA/version/rollback; generated React browser QA vẫn UNVERIFIED |
| Build + browser QA source AI | UNVERIFIED | `agentforge/features/webapps/sandbox.py` | Docker bị thiếu ở máy Owner; CI không chạy generated source |
| Media ảnh tĩnh → MP4 | IMPLEMENTED (bounded) | `agentforge/features/media/assets.py`, `render.py` | Không đồng nghĩa phim AI chuyển động |
| AI Film planner nhiều giờ | IMPLEMENTED (planning) | `agentforge/features/film_studio/long_form.py` | 900 shot được **lập kế hoạch**, chưa render 900 clip |
| ComfyUI motion adapter | IMPLEMENTED (adapter), UNVERIFIED (GPU) | `agentforge/features/film_studio/motion_comfy.py` | Chưa chứng minh model chạy trên GPU 12 GB, chưa import/QA clip |
| Phim AI động 1–3 giờ | NOT IMPLEMENTED | Xem [roadmap](ROADMAP.md) | Chưa có pipeline multi-shot dựng phim dài thực |
| YouTube upload & analytics thật | NOT IMPLEMENTED | `agentforge/growth_pipeline.py` chỉ manual handoff | Không có OAuth/publish API hay doanh thu verified |
| TTS offline | PARTIAL | `agentforge/features/media/render.py` | Cần Piper/voice hoặc Windows SAPI phù hợp |
| ComfyUI image adapter | PARTIAL | `agentforge/features/websites/image_studio.py` | Cần ComfyUI/checkpoint local, không có model cài sẵn |

## Kiểm thử

Windows CI đã có bài Python unittest, JS tests, production builds React Dashboard và NovaMart, Microsoft Edge smoke trên **trusted reference code**, và read-only acceptance. Kiểm tra trạng thái GitHub Actions tại commit đang dùng; bảng này không tự cập nhật CI về sau.

**Chưa xác minh:** chất lượng từ model thật, AI React browser QA/isolated execution, video chuyển động Wan 2.2 trên máy 12 GB, tính nhất quán nhân vật trong phim, hiệu suất dựng hàng trăm shot, YouTube OAuth và khả năng kiếm tiền.

## Đợt 5 — ranh giới nghiệm thu

Code/CI có thêm báo cáo Base V1 **read-only** và bộ contract tests chủ đích; chỉ Owner mới có thể xác nhận login/browser/model/artifact/backup staging trên Windows thật. Không suy ra Base V1 Owner PASS chỉ từ CI; xem [checklist nghiệm thu](verification/base_v1/README.md).

## Các vấn đề ưu tiên

1. AI React Source Revision đã có code; cần thực nghiệm 3 lần chỉnh bằng model và browser QA ở Đợt 7.
2. Film Studio: một clip motion 4 giây thực sự decode được trên GPU Owner; lưu thời gian, VRAM, model/workflow, SHA.
3. Dựng phim: character bible → storyboard có action/camera → shot ledger → clip QA → assembly.
4. Nghiệm thu: automated tests chỉ được ghi PASS với đúng bằng chứng; không tạo status ảo.
5. Productization: cải thiện cài đặt, project export và YouTube publishing sau khi sản xuất video ổn định.

Xem [roadmap](ROADMAP.md) để biết tiêu chí hoàn thành cụ thể.
