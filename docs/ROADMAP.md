# Roadmap khép finding audit 26/11/2026

Baseline main: `9db60df28f242abf9ed199c409409f422d4f89db`. Mục tiêu: một Studio có giám sát, không thêm provider mới trước khi có benchmark. Không tự xóa DB, receipt hay ledger; chỉ archive có chủ đích sau khi đối soát.

| Finding | Trạng thái triển khai (CI và runtime xác minh riêng) | Tiêu chí đóng |
|---|---|---|
| F01 lifecycle production/publishing | IMPLEMENTED (Studio → handoff) | Một thành phẩm đã duyệt đi thẳng tới handoff, SHA kiểm tra lại |
| F02 character references | BLOCKED_RUNTIME | POC conditioning với ảnh đã duyệt, benchmark A/B |
| F03 giới hạn shot local | BLOCKED_RUNTIME | Clip dài hơn được xác nhận trên GPU hoặc adapter khác |
| F04 mất provider ID | PARTIAL (Owner-attested GET-only recovery; duplicate remote IDs rejected) | Đối soát có chứng cứ, không retry mù |
| F05 compatibility production | PARTIAL (strict motion ledger and canonical Studio HTTP/Python creation brief; historical runtime compatibility remains) | Một schema mới, archive DB cũ có chủ đích |
| F06 draft_pipeline | PARTIAL (script analysis and timeline extracted) | Tách theo trách nhiệm, giữ checkpoint/approval |
| F07 readiness quá sớm | IMPLEMENTED | Storyboard theo phương pháp cụ thể không cần quyền media/FFmpeg; approval vẫn chặn |
| F08 OAuth Dashboard | IMPLEMENTED (runtime pending) | Đăng nhập, danh sách model và logout có consent |
| F09 chẩn đoán lỗi | PARTIAL | Mã lỗi an toàn, checkpoint cuối không bị bỏ qua khi offload lỗi; chưa có logging toàn hệ thống |
| F10 benchmark/cost | PARTIAL (persisted usage and attempt metrics) | Đo thời gian, chi phí và chất lượng trên output thật |
| F11 QA thực tế | BLOCKED_RUNTIME | Owner đánh giá nhiều phim, ghi kết quả |
| F12 hygiene tài liệu/test | PARTIAL | Tài liệu setup và CI ChatGPT extra đồng bộ; dọn phần còn lại khi bỏ compatibility |

## Cổng nghiệm thu

1. Foundation: schema và lifecycle nhất quán, test API/worker/browser, CI pass.
2. Runtime: lỗi chẩn đoán được, reconciliation fail-closed, OAuth thật do Owner xác nhận.
3. Quality: benchmark cùng kịch bản và nhân vật; không dùng mock API hoặc FFmpeg decode làm chứng cứ chất lượng sáng tạo.

## Hợp đồng Studio hiện hành

- Tạo production qua HTTP và Python chỉ dùng `duration_mode` là `auto` hoặc `manual`, `scene_count: null`, và `mode` rõ ràng. AI lập số cảnh; Owner duyệt storyboard trước khi sinh media. Kế hoạch 30 giây hiện hành không yêu cầu trường trọng số preset cũ. Nếu chọn tuyến sản xuất, gửi cả `route_strategy` và `max_cloud_seconds`.
- Không hỗ trợ trường `motion_approved` hay API sửa cảnh không có phiên bản. Mọi chỉnh sửa đi qua `storyboard-*` với SHA hiện tại.
- Các bản ghi lịch sử vẫn có thể đọc, xác minh và đối soát theo checkpoint gốc; không tự chuyển đổi SHA hoặc xóa dữ liệu. Không tạo production mới bằng preset. Chỉ giữ planner/timeline preset để xử lý checkpoint lịch sử; chưa đóng F05.
