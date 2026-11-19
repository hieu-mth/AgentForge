# Trạng thái source — AgentForge Video Studio

Mục tiêu cleanup: một nền tảng local-first cho Film Studio, Character Registry, media/image generation, Model Hub, Owner session và Publishing. Git chỉ giữ các thành phần hiện hành; các route ngoài phạm vi Studio không được thực thi.

Trạng thái **source/CI chỉ chốt khi Windows Python tests, React build/browser smoke, docs/hygiene và FFmpeg fixture đều PASS trên cùng commit**. Nghiệm thu GPU ComfyUI, generated video thực, visual continuity, TTS ngôn ngữ và tài khoản YouTube phải làm riêng trên máy Owner.

Không xóa/migrate dữ liệu của Owner: SQLite cũ có thể vẫn tồn tại trong `data/` nhưng không có route nghiệp vụ để thực thi lại. Model Hub đọc hồ sơ Owner cũ mà không tự sửa dữ liệu; model chỉ có trong TOML trước đây không được tự tái tạo. Model/route mới được Owner thêm từ Dashboard vào SQLite.

Xem [cấu trúc](architecture/REPOSITORY_STRUCTURE.md) và [Owner gate](verification/OWNER_PRODUCTION_GATE.md).
