# Model Hub — local-first Video Studio

Model definitions: \`config/models.toml\`. Route catalog: \`config/task_routes.toml\` gồm \`general.text\`, \`film.storyboard\`, \`film.motion\`, \`image.generate\`, \`ops.monitor\`.

Các route film/image là **CONFIG_ONLY** (không tự chạy GPU), ops.monitor deterministic. Cấu hình Owner được ghi ở \`data/company/model_hub.sqlite3\` với revision check, không ghi token hoặc secret vào Git. Profile tồn tại không đồng nghĩa model đã tải, đang online hay VRAM đủ.

Chỉ ComfyUI loopback + manifest/Owner approvals trong Film Studio mới được dùng để submit GPU thật. Không tự fallback lên cloud. Overlay SQLite lịch sử có khóa route không còn hỗ trợ vẫn đọc được, nhưng route đó không xuất hiện trong catalog hiện hành và không được thực thi lại; GET không tự rewrite database.

Xem [cấu trúc](REPOSITORY_STRUCTURE.md) và [runtime Owner](../verification/RUNTIME.md).
