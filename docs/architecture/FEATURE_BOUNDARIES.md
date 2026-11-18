# Ranh giới capability — AgentForge Video Studio

Mục tiêu: giữ core ổn định, chỉ một Owner API, khả năng thay model qua config, các nguồn dữ liệu local không bị tự động ghi đè.

- **Owner API**: xác thực/session/CSRF, transport/response. Không chạy GPU/model chỉ vì GET hoặc reload.
- **Core/Task lifecycle**: lưu task, approval trước khi gọi công cụ, không retry âm thầm khi trạng thái thực thi không chắc chắn.
- **Film Studio**: shot manifest, character continuity, signed media receipts, review/publishing. Không tự coi mock MP4 là video AI hoàn chỉnh.
- **Shared Media**: tạo/thu thập ảnh, render/FFmpeg, codec và kiểm chứng nguồn; tái sử dụng thay vì import Website Builder.
- **AI / Model Hub**: cấu hình provider/worker, local-first, trạng thái readiness không thay thế inference thật.
- **Integrations**: ComfyUI localhost, YouTube private-only adapter; chỉ thực hiện khi Owner cấp quyền chính xác.
- **Storage/Ops**: DB/backup/retention, không xóa Owner workspace, model, credential hoặc video khi cleanup.

`agentforge.domains/` shim trung gian đã được loại bỏ; mã mới chỉ import canonical feature. Những package nghiệp vụ lịch sử còn tồn tạm trong quá trình dọn source **không** được khôi phục qua HTTP/API.

[Current structure](REPOSITORY_STRUCTURE.md) · [Film pilot](FILM_MOTION_12GB_PILOT.md).
