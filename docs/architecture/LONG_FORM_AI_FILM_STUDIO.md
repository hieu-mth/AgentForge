# Film Studio — local-first

## Model routing và tiếp tục production

Studio đọc các capability đã phân công từ một snapshot SQLite của Model Hub. Lập kế hoạch, storyboard và ảnh cần route local tương thích. Video động còn cần route motion. Chọn nhân vật từ thư viện chỉ chạy khi có phân công riêng. Studio không dùng model mặc định, đề xuất tự động hay cloud fallback để thay cho route Owner đã chọn.

Bản nháp mới lưu fingerprint của hồ sơ đã chọn ngay khi nhận việc. Storyboard SHA bao gồm các fingerprint đó và danh tính adapter motion hiện có. Khi duyệt, Studio giữ thêm dấu nhận dạng cấu hình ComfyUI Portable cho motion. Resume đối chiếu các route liên quan trước khi gọi adapter. Thay đổi Hồ sơ Model Hub ngoài các route này không làm mất hiệu lực duyệt. Rollback về đúng cấu hình đã duyệt có thể cho phép tiếp tục, dù số revision đã tăng.

Bản nháp cũ dùng revision gốc và dữ liệu lịch sử Model Hub để xác minh route khi revision hiện tại khác. Nếu không đủ bằng chứng, Studio giữ checkpoint và yêu cầu khôi phục cấu hình. Mất kết nối ComfyUI không thay đổi danh tính runtime. Job có trạng thái chưa chắc chắn vẫn phải đối soát ledger trước khi tiếp tục. Các ảnh và clip đã xác minh được đọc lại từ checkpoint.

Fingerprint pin cấu hình profile và preset, không xác nhận bytes của tag Ollama hoặc weights FLUX đã bị thay thế tại chỗ trên runtime. LTX tiếp tục xác minh SHA checkpoint và encoder trước dispatch. Kiểm thử fixture không xác nhận inference GPU trên máy Owner.

Pipeline hiện có trong source: lập immutable film plan và shot slots → Owner review → ComfyUI motion job một lượt đã duyệt → nhận clip MP4, verify SHA/frames/FFmpeg → versioned production + optional local TTS → render episode có receipt → Owner review → publishing handoff local/optional private-only YouTube CLI.

Quy trình **không** tự tạo đầy đủ phim từ một prompt, không tự kiểm visual identity/continuity và không bảo đảm chất lượng media. Mỗi shot cần workflow, weights, nguồn nội dung và quyền được kiểm chứng. Tooling cho phép one-shot pilot; hiệu suất và khả năng dựng phim dài chưa được thử trên PC Owner.

- [Motion](../verification/MOTION.md)
- [Production](../verification/PRODUCTION.md)
- [Publishing](../verification/PUBLISHING.md)
- [Owner runtime acceptance](../verification/OWNER_PRODUCTION_GATE.md)

Mọi dữ liệu sản xuất và model giữ trong các vùng local của Owner, không thuộc cleanup Git.
