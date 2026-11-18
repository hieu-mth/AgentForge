# Trạng thái source — AgentForge Video Studio

Mục tiêu cleanup: một nền tảng local-first cho Film Studio, Character Registry, media/image generation, Model Hub, Owner session và Publishing. Phần Goal/Skill/Website/Webapp/Growth/Analytics cũ đã được loại khỏi Git ở nhánh cleanup; không còn được route vào Owner API.

Trạng thái **source/CI chỉ chốt khi Windows Python tests, React build/browser smoke, docs/hygiene và FFmpeg fixture đều PASS trên cùng commit**. Nghiệm thu GPU ComfyUI, generated video thực, visual continuity, TTS ngôn ngữ và tài khoản YouTube phải làm riêng trên máy Owner.

Không xóa/migrate dữ liệu của Owner: SQLite cũ có thể vẫn tồn tại trong \`data/\` nhưng không có route nghiệp vụ để thực thi lại. Model Hub đọc overlay cũ mà không tự sửa dữ liệu.

Xem [cấu trúc](architecture/REPOSITORY_STRUCTURE.md) và [Owner gate](verification/OWNER_PRODUCTION_GATE.md).
