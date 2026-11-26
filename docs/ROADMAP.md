# Roadmap khép finding audit 26/11/2026

Baseline main: `9db60df28f242abf9ed199c409409f422d4f89db`. Mục tiêu: một Studio có giám sát, không thêm provider mới trước khi có benchmark. Không tự xóa DB, receipt hay ledger; chỉ archive có chủ đích sau khi đối soát.

| Finding | Trạng thái triển khai (CI và runtime xác minh riêng) | Tiêu chí đóng |
|---|---|---|
| F01 lifecycle production/publishing | IMPLEMENTED (Studio → handoff) | Một thành phẩm đã duyệt đi thẳng tới handoff, SHA kiểm tra lại |
| F02 character references | BLOCKED_RUNTIME | POC conditioning với ảnh đã duyệt, benchmark A/B |
| F03 giới hạn shot local | BLOCKED_RUNTIME | Clip dài hơn được xác nhận trên GPU hoặc adapter khác |
| F04 mất provider ID | PARTIAL (Owner-attested GET-only recovery; duplicate remote IDs rejected; cancellation validates ledger ownership and provider metadata) | Đối soát có chứng cứ, không retry mù |
| F05 compatibility production | PARTIAL (strict motion ledger and canonical creation and planner; historical timeline/receipt compatibility remains) | Một schema mới, archive DB cũ có chủ đích |
| F06 draft_pipeline | PARTIAL (script analysis, timeline, SQLite draft store and worker attempt transitions extracted) | Tách theo trách nhiệm, giữ checkpoint/approval |
| F07 readiness quá sớm | IMPLEMENTED | Storyboard theo phương pháp cụ thể không cần quyền media/FFmpeg; approval vẫn chặn |
| F08 OAuth Dashboard | IMPLEMENTED (runtime pending) | Đăng nhập, danh sách model và logout có consent |
| F09 chẩn đoán lỗi | PARTIAL | Mã lỗi an toàn, checkpoint cuối không bị bỏ qua khi offload lỗi; worker launch failure có mã lỗi an toàn; chưa có logging toàn hệ thống |
| F10 benchmark/cost | PARTIAL (persisted usage, attempt metrics and sample coverage) | Đo thời gian, chi phí và chất lượng trên output thật |
| F11 QA thực tế | BLOCKED_RUNTIME | Owner đánh giá nhiều phim, ghi kết quả |
| F12 hygiene tài liệu/test | PARTIAL | Tài liệu setup và CI ChatGPT extra đồng bộ; dọn phần còn lại khi bỏ compatibility |

## Cổng nghiệm thu

1. Foundation: schema và lifecycle nhất quán, test API/worker/browser, CI pass.
2. Runtime: lỗi chẩn đoán được, reconciliation fail-closed, OAuth thật do Owner xác nhận.
3. Quality: benchmark cùng kịch bản và nhân vật; không dùng mock API hoặc FFmpeg decode làm chứng cứ chất lượng sáng tạo.

## Hợp đồng Studio hiện hành

- Tạo production qua HTTP và Python chỉ dùng `duration_mode` là `auto` hoặc `manual`, `scene_count: null`, và `mode` rõ ràng. AI lập số cảnh; Owner duyệt storyboard trước khi sinh media. Kế hoạch 30 giây hiện hành không yêu cầu trường trọng số preset cũ. Nếu chọn tuyến sản xuất, gửi cả `route_strategy` và `max_cloud_seconds`.
- Không hỗ trợ trường `motion_approved` hay API sửa cảnh không có phiên bản. Mọi chỉnh sửa đi qua `storyboard-*` với SHA hiện tại.
- Các bản ghi lịch sử vẫn có thể đọc, xác minh và đối soát theo checkpoint gốc; không tự chuyển đổi SHA hoặc xóa dữ liệu. Không tạo production mới bằng preset. Planner preset đã bị loại bỏ; bản ghi cũ chưa có storyboard phải tạo production mới từ nội dung gốc, không tự gọi model hoặc sửa dữ liệu. Timeline/receipt preset vẫn được giữ để xác minh, chỉnh sửa theo phiên bản và tiếp tục storyboard đã lưu; chưa đóng F05.

Số liệu Overview phân biệt dữ liệu chưa ghi nhận và giá trị 0; hiển thị số bản nháp có counter và attempt hoàn tất. Đây là số liệu đặt chỗ và attempt gần nhất, không phải hóa đơn hay benchmark end-to-end.

## Ranh giới lưu trữ Studio

`draft_store.py` quản lý truy vấn SQLite, đọc/ghi checkpoint, cancellation và hàng đợi. Pipeline giữ quyết định lifecycle, khóa worker và phạm vi transaction admission/deletion. Không đổi schema, đường dẫn DB, digest hoặc cơ chế xác minh media.

`draft_lifecycle.py` chứa chuyển trạng thái attempt và cách trình bày bản ghi gián đoạn. Worker launch thất bại khôi phục checkpoint trước đó; hủy production kiểm tra đúng ID worker, không che khuất trạng thái cần đối soát. Pipeline vẫn sở hữu thread, khóa và điều phối media.

Cloud motion đọc ledger bằng SQLite read-only. Trước khi đối soát hủy, kiểm tra production/model/thời lượng của mọi shot và job unresolved không gắn checkpoint; chỉ GET endpoint hợp lệ, không POST lại. Metadata model/thời lượng nếu provider trả phải khớp ledger. Chưa có runtime provider thật.

## Baseline nghiệm thu source 26/11/2026

Main `4afd7ab8b32cf1c8155966e3c72c11b1463ee1b2` sau PR #187. CI của head PR #187: run 45773586846, PASS; 329 Python tests (1 skipped), 25 Dashboard unit tests, 9 cloud integration tests (chạy riêng, có thể trùng với regression suite), Edge browser smoke, FFmpeg fixture, Markdown và source hygiene PASS. Git tree có 190 tracked files (73 agentforge, 52 dashboard, 42 tests, 7 docs, 9 scripts, 2 examples, 5 tệp root/CI). Tất cả nhóm optional dependency Python đều có đường sử dụng: Pillow/FFmpeg, JWT/crypto cho ChatGPT OAuth, Google client/OAuth cho private upload. Không xóa công cụ nâng cao còn được Studio gọi. Đây là review theo inventory và các đường chạy trọng yếu, chưa phải phân tích reachability toàn bộ source hay SCA/secret history scan. Không coi CI fixture là runtime GPU, chất lượng điện ảnh, OAuth thật hoặc chi phí thực tế. Giữ F02/F03/F08/F10/F11 cho nghiệm thu runtime; F05 còn historical receipts/timeline, F04/F09 còn provider thật và chẩn đoán toàn hệ thống.
