# Roadmap cleanup — chỉ thu gọn nền tảng

1. **Cắt legacy ở entrypoint:** Dashboard, API Owner, CLI, worker, scheduler. Không giữ route chỉ vì tương thích lịch sử.
2. **Dọn dependency theo chiều sử dụng:** Film Studio giữ những utility thực sự cần (FFmpeg, media render, security, model routing); bỏ Website/Webapp/Mattress/Growth và Media Workflow V1.5 khi không còn import.
3. **Dọn kiểm thử và tài liệu:** loại test và Markdown của sản phẩm đã bỏ; cập nhật docs, scripts, CI theo phạm vi video.
4. **Nghiệm thu nền tảng:** Python unit tests, Dashboard build, browser smoke, docs links, source hygiene; sau đó Owner kiểm tra GPU/ComfyUI/FFmpeg thật.

**Definition of Done:** không còn import/route/source legacy nghiệp vụ trong runtime chính; CI xanh; cấu trúc và tài liệu khớp source. Không dùng mock test để tuyên bố video thực đã chạy.
