# Trạng thái AgentForge — Video-first cleanup

Cập nhật 18/11/2026. Đây là trạng thái source, không phải chứng nhận runtime.

| Hạng mục | Trạng thái |
| --- | --- |
| Dashboard video-first | CI React build, navigation và Edge browser smoke PASS (Đợt 1) |
| Character Registry | Có code, runtime chưa xác minh |
| Film Studio production/assembly | Có code, GPU/visual continuity chưa nghiệm thu |
| Video project inventory | Chỉ đọc Film Studio |
| Website/Webapp/Growth | API Owner đã gỡ; Đợt 3 bỏ shim, manifest và nhiều source cũ; còn 29 file feature legacy cần phân loại caller ở final audit |
| Mattress backend | Đã xóa 4 module code; không xóa dữ liệu Owner |
| Media Workflow V1.5 | API và module workflow đã gỡ; dữ liệu lịch sử không bị xóa |
| AI Image / ComfyUI | Transport riêng trong `features/media/comfy_image.py`, không phụ thuộc Website Builder |
| Publishing | Owner-gated; tách Growth Store, chỉ cho release mới không gắn Campaign; chưa xác minh YouTube thực |
| CI | Đợt 3 PASS tại `f55d3172` (2 job Windows SUCCESS; 777 Python tests, 112 contract tests); GPU/Owner runtime chưa xác minh |

Không phát triển tính năng mới trong đợt cleanup. Không xóa dữ liệu local, credential hoặc output của Owner.

Bằng chứng nghiệm thu Đợt 1: [PHASE1_ACCEPTANCE.md](audits/PHASE1_ACCEPTANCE.md). Cleanup backend cũ tiếp tục ở Đợt 2–3.

Bằng chứng nghiệm thu backend Đợt 2: [PHASE2_BACKEND_ACCEPTANCE.md](audits/PHASE2_BACKEND_ACCEPTANCE.md). Source/manifest/test/docs legacy còn lại tiếp tục dọn theo dependency ở Đợt 3.

Đợt 3 đã có [báo cáo nghiệm thu](audits/PHASE3_CLEANUP_ACCEPTANCE.md). Đợt 4 đang dọn sâu: đã xóa placeholder `templates/`, bỏ phép quét tài liệu của thư mục này, xóa runbook Docker Webapp cũ, thay Owner production gate và runtime checklist bằng phạm vi video, bỏ Analytics Dataset khỏi acceptance và sửa entrypoint Dashboard. **Chưa nghiệm thu Đợt 4**: 29 file feature legacy, root aliases, Skill Registry (23 manifest; Web/Analytics/Media cũ), skill adapters, worker/config/test/CI callers và một số docs lịch sử vẫn phải được xử lý đồng bộ. Không tuyên bố repository sạch hoặc CI PASS cho những commit Đợt 4 chưa kiểm chứng.
