# Motion — ComfyUI local

Studio sử dụng model motion do Owner đăng ký và phân công trong Model Hub. Preset LTX 2B distilled FP8 I2V hiện hành sử dụng ảnh nguồn, 512×288, tối đa 49 frame ở 24 FPS. Wan 2.2 TI2V 5B FP16 bị chặn dispatch do rủi ro cạn Windows commit; biên nhận cũ vẫn có thể đọc.

## Vận hành

1. Cấu hình ComfyUI loopback và launcher trong Dashboard; đăng ký model, encoder và workflow tương thích.
2. Kiểm tra readiness, FFmpeg/ffprobe, RAM, Windows commit, VRAM và queue.
3. Tạo storyboard, kiểm timeline và duyệt đúng digest trước khi tạo media.
4. Theo dõi job; nếu kết quả submit chưa rõ, đối soát history trước khi tiếp tục. Không gửi lại mù.
5. Kiểm clip bằng SHA, frame count, kích thước, FPS và FFmpeg decode; xem trực tiếp để đánh giá motion và continuity.

Không tự tải weights, cài custom nodes hoặc fallback cloud. Không giảm resource guard để vượt lỗi bộ nhớ. Metadata readiness và technical QA không chứng minh chất lượng hình ảnh.

Xem [hướng dẫn chạy](../../README.md), [runtime](RUNTIME.md) và [production gate](OWNER_PRODUCTION_GATE.md).
