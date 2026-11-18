# Trạng thái AgentForge — Video-first cleanup

Cập nhật 18/11/2026. Đây là trạng thái source, không phải chứng nhận runtime.

| Hạng mục | Trạng thái |
| --- | --- |
| Dashboard video-first | CI React build, navigation và Edge browser smoke PASS (Đợt 1) |
| Character Registry | Có code, runtime chưa xác minh |
| Film Studio production/assembly | Có code, GPU/visual continuity chưa nghiệm thu |
| Video project inventory | Chỉ đọc Film Studio |
| Website/Webapp/Growth | API Owner chính đã gỡ; package, alias, skill/CLI lịch sử vẫn còn để cleanup Đợt 3 |
| Mattress backend | Đã xóa 4 module code; không xóa dữ liệu Owner |
| Media Workflow V1.5 | API cũ đã gỡ; module, dữ liệu lịch sử chưa xóa |
| AI Image / ComfyUI | Transport riêng trong `features/media/comfy_image.py`, không phụ thuộc Website Builder |
| Publishing | Owner-gated; tách Growth Store, chỉ cho release mới không gắn Campaign; chưa xác minh YouTube thực |
| CI | Đợt 2 runtime PASS tại `e353087e` (2 job Windows SUCCESS); Owner GPU/runtime chưa xác minh |

Không phát triển tính năng mới trong đợt cleanup. Không xóa dữ liệu local, credential hoặc output của Owner.

Bằng chứng nghiệm thu Đợt 1: [PHASE1_ACCEPTANCE.md](audits/PHASE1_ACCEPTANCE.md). Cleanup backend cũ tiếp tục ở Đợt 2–3.

Bằng chứng nghiệm thu backend Đợt 2: [PHASE2_BACKEND_ACCEPTANCE.md](audits/PHASE2_BACKEND_ACCEPTANCE.md). Source/manifest/test/docs legacy còn lại tiếp tục dọn theo dependency ở Đợt 3.

Đợt 3 đang loại các alias/module/test và tài liệu lịch sử; kết quả cuối phải đối chiếu GitHub CI và danh sách dependency còn tồn.
