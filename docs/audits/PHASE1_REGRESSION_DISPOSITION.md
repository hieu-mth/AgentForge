# Đợt 1 — Phân loại và nghiệm thu regression

Ngày kiểm: 2026-11-18. Phạm vi: AgentForge Video Studio/Film Studio, Owner API, model, image/media infrastructure, security và local state.

## Vì sao giảm bớt các test lịch sử?

NovaMart React template và API Webapp/Website Proposal/Mattress đã bị gỡ khỏi sản phẩm trước Đợt 1. Những test liên quan kiểm tra **contract không còn được cung cấp** và tạo hàng loạt lỗi phụ thuộc chung. Việc khôi phục NovaMart chỉ để sửa CI sẽ trái quyết định video-first. Danh sách test chỉ phục vụ những contract đã bỏ được xóa khỏi HEAD (vẫn truy xuất được trong Git history).

- `tests/test_acceptance_http.py`
- `tests/test_artifact_acceptance.py`
- `tests/test_generated_execution_boundaries.py`
- `tests/test_locked_toolchain.py`
- `tests/test_m4_webapps_features.py`
- `tests/test_source_syntax.py`
- `tests/test_trusted_template_layout.py`
- `tests/test_v53_developer_metadata.py`
- `tests/test_v54_developer_safety_diagnostics.py`
- `tests/test_v5_company.py`
- `tests/test_wave6_source_revision.py`
- `tests/test_wave7_product_qa_export.py`
- `tests/test_webapp_builder_v40.py`
- `tests/test_webapp_developer_v42b.py`
- `tests/test_webapp_goal_v40.py`
- `tests/test_webapp_revision_http_v41.py`
- `tests/test_webapp_revision_v41.py`
- `tests/test_webapp_sandbox_v42.py`
- `tests/test_website_feedback_v26.py`
- `tests/test_website_visual_preview.py`
- `tests/test_wave6_mattress_mvp.py`

## Những kiểm thử phải giữ

- Auth/session/CSRF, Owner read-only và explicit approval
- Film motion, production, publishing, Character Registry và Video Projects
- Model routing/readiness, ComfyUI/image bridge và FFmpeg validation
- Operational recovery, data retention/backups, source hygiene
- Các kiểm thử core/worker/security không phụ thuộc sản phẩm đã bỏ

Các HTTP film/ops test trước đây dùng `tests.test_webapp_revision_http_v41` đã được chuyển sang `tests.owner_http_fixture`, sử dụng server thật nhưng không dựng đề xuất React. Không loại test film/publishing chỉ vì fixtures lỗi.

## Nguyên tắc nghiệm thu

Không dùng `skip`, `expectedFailure` hoặc tắt step CI để làm giả kết quả. CI hiện có phải kiểm tra docs, source hygiene, React build/browser smoke, toàn bộ test còn hợp lệ, FFmpeg và local Windows acceptance. CI PASS chỉ xác nhận regression trên fixture/runner Windows; không chứng nhận GPU, model và video thực tế trên máy Owner.

Các module backend của sản phẩm cũ có thể vẫn ở source cho tới Đợt 2 cleanup dependency; chúng không được coi là sản phẩm còn hỗ trợ.
