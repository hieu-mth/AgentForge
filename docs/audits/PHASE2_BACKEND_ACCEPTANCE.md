# AgentForge — Nghiệm thu Đợt 2: Backend & Dependency

Ngày: 18/11/2026. **Verdict: PASS cho luồng Owner API / Film Studio chính trên Windows CI.** Chưa phải xác nhận đã xóa toàn bộ source legacy hoặc sản xuất phim thật trên máy Owner.

## Mốc kiểm chứng

- Commit nguồn đã kiểm chứng: [`e353087e`](https://github.com/hieu-mth/AgentForge/commit/e353087e13aec015f059687bcb1c4e4d8e5b0a7d).
- [GitHub Actions #44271435311](https://github.com/hieu-mth/AgentForge/actions/runs/44271435311): **SUCCESS**, cả 2 job.
- Full Windows Python 3.13: **941 tests, 0 failures, 0 errors, 2 skipped**.
- Video Studio PowerShell contract acceptance: **111 tests PASS**.
- Independent Owner session/CSRF, retired route gating, Film project routing: **7 tests PASS**.
- React navigation, Ant Design build, Edge browser smoke, built asset routing: **PASS**.
- Docs links, source hygiene, compatibility audit, wheel/package check: **PASS**.
- FFmpeg encode/decode trên video fixture trong Windows CI; PowerShell preflight và read-only Owner acceptance: **PASS**.
- Không có GPU/ComfyUI/YouTube thực, checkpoint hoặc chất lượng chuyển động được kiểm chứng trên máy Owner.

## Các thay đổi nguồn được nghiệm thu

1. **Publishing:** không còn gọi Growth Store khi chuẩn bị release. Metadata release lịch sử giữ trường `campaign` nullable; release mới từ chối giá trị khác null. Khóa SHA, quyền duyệt Owner và trạng thái private/manual handoff vẫn giữ.
2. **ComfyUI/Image:** thêm `features/media/comfy_image.py` làm bộ truyền ComfyUI local-loopback dùng chung. `features/media/visual_jobs.py` không còn import Website Builder/Product Builder; chỉ chấp nhận tác vụ ảnh/video, từ chối `website` trước khi ghi dữ liệu hoặc dispatch GPU.
3. **Owner API:** bỏ endpoint đọc/ghi của Media V1.5, Website Images, Proposal/Webapp, Growth Campaign, draft/video approval cũ; giữ Film motion, film render/voice, character, image/video visual jobs, Publishing, Model Hub, ops, artifact báo cáo và retention.
4. **Owner Bootstrap:** bỏ Growth scorecard, Company V2, Quality V1.4, Autopilot V1.3 và Website proposal khỏi dữ liệu điều hành. Không đọc các business DB khi phục vụ bootstrap chính.
5. **Retired workflow:** API tạo goal/preflight/schedule mới từ chối Website/Webapp/Growth, Media V1.5, creative storyboard legacy, kể cả workflow.compose có bước con thuộc nhóm đã nghỉ. Record lịch sử vẫn được phép đọc.
6. **Lịch cũ:** scheduler tick từ chối tạo goal mới từ lịch Website/Growth/Media đã nghỉ, không consume slot, không dispatch runner; lịch cũ vẫn tồn tại để Owner kiểm tra.
7. **Mattress:** xóa 4 module backend `features/mattress_sales`; bỏ tham số SQLite mattress không sử dụng khỏi `create_server`.
8. **Kiểm thử ranh giới:** thêm `tests/test_video_backend_boundary.py`, cập nhật các test fail-closed và giữ các kiểm thử core security/film/publishing. Toàn bộ CI cũ vẫn hoạt động; không skip hàng loạt để ép xanh.

## Những phần CHƯA được xóa vật lý

- Các package Website Builder (`agentforge/features/websites/`), Webapp Builder (`agentforge/features/webapps/`), Growth (`agentforge/features/growth/`) và Media Workflow V1.5 vẫn còn trong source/alias/CLI cùng các test và skill manifest lịch sử. Một số vẫn có thể được gọi bằng Python/CLI trực tiếp, **không thuộc Owner API video-first được nghiệm thu**.
- Phần kiểm tra goal lịch sử có thể vẫn import preflight/dữ liệu Growth cũ để xác thực archived goal. Chưa xác nhận toàn repository không còn bất cứ import legacy nào.
- Việc xóa các alias, worker, skills, CLI, file Python/JS, cấu hình thừa và tài liệu Markdown lịch sử phải tiến hành theo dependency cùng test tại **Đợt 3**, đặc biệt để không làm mất khả năng truy xuất output/SQLite Owner.
- Đợt 4 vẫn cần final cross-module audit và Owner hardware/media QA riêng.

## Kiểm soát dữ liệu và giới hạn

Không có bước xóa/migrate trực tiếp `data/`, `workspace/`, model checkpoint, API key hay video/ảnh đã tạo trên máy Owner. GitHub CI chỉ dùng fixture tạm; không có bằng chứng khẳng định mọi runtime local trên Windows Owner đã PASS.

## Quyết định

**Chốt Đợt 2 trong phạm vi cô lập runtime backend chính và CI.** Đợt 3 nhận các hạng mục source/manifest/test/docs legacy còn tồn, không chấp nhận kết luận “đã clean toàn bộ repository” trước khi đối chiếu dependency thực tế và CI xanh.
