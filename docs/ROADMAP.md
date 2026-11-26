# Roadmap khép finding audit 26/11/2026

Baseline main: `9db60df28f242abf9ed199c409409f422d4f89db`. Mục tiêu: một Studio có giám sát, không thêm provider mới trước khi có benchmark. Không tự xóa DB, receipt hay ledger; chỉ archive có chủ đích sau khi đối soát.

| Finding | Trạng thái trên nhánh này | Tiêu chí đóng |
|---|---|---|
| F01 lifecycle production/publishing | IMPLEMENTED (Studio → handoff) | Một thành phẩm đã duyệt đi thẳng tới handoff, SHA kiểm tra lại |
| F02 character references | BLOCKED_RUNTIME | POC conditioning với ảnh đã duyệt, benchmark A/B |
| F03 giới hạn shot local | BLOCKED_RUNTIME | Clip dài hơn được xác nhận trên GPU hoặc adapter khác |
| F04 mất provider ID | PARTIAL (Owner-attested GET-only recovery) | Đối soát có chứng cứ, không retry mù |
| F05 compatibility production | PARTIAL (motion ledger schema strict) | Một schema mới, archive DB cũ có chủ đích |
| F06 draft_pipeline | PARTIAL (pure script analysis extracted) | Tách theo trách nhiệm, giữ checkpoint/approval |
| F07 readiness quá sớm | IMPLEMENTED | Storyboard theo phương pháp cụ thể không cần quyền media/FFmpeg; approval vẫn chặn |
| F08 OAuth Dashboard | IMPLEMENTED (runtime pending) | Đăng nhập, danh sách model và logout có consent |
| F09 chẩn đoán lỗi | PARTIAL | Mã lỗi an toàn cho exception bất ngờ, CLI OAuth rõ hơn; chưa có logging toàn hệ thống |
| F10 benchmark/cost | OPEN | Đo thời gian, chi phí và chất lượng trên output thật |
| F11 QA thực tế | BLOCKED_RUNTIME | Owner đánh giá nhiều phim, ghi kết quả |
| F12 hygiene tài liệu/test | PARTIAL | Tài liệu setup và CI ChatGPT extra đồng bộ; dọn phần còn lại khi bỏ compatibility |

## Cổng nghiệm thu

1. Foundation: schema và lifecycle nhất quán, test API/worker/browser, CI pass.
2. Runtime: lỗi chẩn đoán được, reconciliation fail-closed, OAuth thật do Owner xác nhận.
3. Quality: benchmark cùng kịch bản và nhân vật; không dùng mock API hoặc FFmpeg decode làm chứng cứ chất lượng sáng tạo.
