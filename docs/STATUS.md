# AgentForge — Trạng thái thực tế

**Baseline tính năng:** sau PR #61 (09/11/2026); **đường dẫn code hiện tại:** M1 `dashboard/`, M2 `agentforge/` ở root; M3 canonical HTTP ở `agentforge/api/`. M6/M7 thêm Model Hub quản lý profile và text task routing; ComfyUI video/image chưa kết nối qua route mới.

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
| Artifact acceptance gắn SHA | IMPLEMENTED | `agentforge/core/artifact_acceptance.py` | Workflow `SUCCEEDED` chưa chắc artifact `ACCEPTED` |
| Static Website Builder | PARTIAL | `agentforge/domains/websites/` | Thiết kế và section bị giới hạn bởi schema; không có backend chung |
| Marketplace React demo | PARTIAL | `agentforge/domains/webapps/builder.py`, `templates/novamart/` | Cart/search demo, không có checkout thanh toán |
| AI React Developer | PARTIAL | `agentforge/domains/webapps/developer.py` | Danh sách file giới hạn; source là đề xuất, không tự chạy |
| Source revision cho AI React | NOT IMPLEMENTED | `agentforge/api/routes/products.py` hiện trả về `PermissionError` | Website/marketplace **có** revision riêng theo data/schema, không phải sửa source AI |
| Build + browser QA source AI | UNVERIFIED | `agentforge/domains/webapps/sandbox.py` | Docker bị thiếu ở máy Owner; CI không chạy generated source |
| Media ảnh tĩnh → MP4 | IMPLEMENTED (bounded) | `agentforge/domains/media/assets.py`, `render.py` | Không đồng nghĩa phim AI chuyển động |
| AI Film planner nhiều giờ | IMPLEMENTED (planning) | `agentforge/domains/media/long_form.py` | 900 shot được **lập kế hoạch**, chưa render 900 clip |
| ComfyUI motion adapter | IMPLEMENTED (adapter), UNVERIFIED (GPU) | `agentforge/domains/media/motion_comfy.py` | Chưa chứng minh model chạy trên GPU 12 GB, chưa import/QA clip |
| Phim AI động 1–3 giờ | NOT IMPLEMENTED | Xem [roadmap](ROADMAP.md) | Chưa có pipeline multi-shot dựng phim dài thực |
| YouTube upload & analytics thật | NOT IMPLEMENTED | `agentforge/growth_pipeline.py` chỉ manual handoff | Không có OAuth/publish API hay doanh thu verified |
| TTS offline | PARTIAL | `agentforge/domains/media/render.py` | Cần Piper/voice hoặc Windows SAPI phù hợp |
| ComfyUI image adapter | PARTIAL | `agentforge/domains/websites/image_studio.py` | Cần ComfyUI/checkpoint local, không có model cài sẵn |

## Kiểm thử

Windows CI đã có bài Python unittest, JS tests, production builds React Dashboard và NovaMart, Microsoft Edge smoke trên **trusted reference code**, và read-only acceptance. Kiểm tra trạng thái GitHub Actions tại commit đang dùng; bảng này không tự cập nhật CI về sau.

**Chưa xác minh:** chất lượng từ model thật, AI React browser QA/isolated execution, video chuyển động Wan 2.2 trên máy 12 GB, tính nhất quán nhân vật trong phim, hiệu suất dựng hàng trăm shot, YouTube OAuth và khả năng kiếm tiền.

## Các vấn đề ưu tiên

1. AI React Source Revision: sửa code cũ theo feedback, diff, version, rollback và no-op guard.
2. Film Studio: một clip motion 4 giây thực sự decode được trên GPU Owner; lưu thời gian, VRAM, model/workflow, SHA.
3. Dựng phim: character bible → storyboard có action/camera → shot ledger → clip QA → assembly.
4. Nghiệm thu: automated tests chỉ được ghi PASS với đúng bằng chứng; không tạo status ảo.
5. Productization: cải thiện cài đặt, project export và YouTube publishing sau khi sản xuất video ổn định.

Xem [roadmap](ROADMAP.md) để biết tiêu chí hoàn thành cụ thể.
