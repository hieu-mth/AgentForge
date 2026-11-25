# Model Hub — SQLite-only, local-first

**Không còn thư mục `config/` hay model mặc định trong Git.** Owner đăng ký, chỉnh sửa và xóa profile từ **Cài đặt → Model AI**. Một máy mới có **0 model đã đăng ký**. Ollama hoặc ComfyUI được phát hiện bởi trang Môi trường không đồng nghĩa được tự thêm vào Model Hub.

- Nguồn dữ liệu duy nhất của model profile, các model được gán cho tác vụ và chính sách điều phối: `data/company/model_hub.sqlite3` (ignored), revision/CAS, rollback transaction và Owner confirmation.
- Danh mục capability (`general.text`, `film.storyboard`, `film.motion`, `image.generate`, `ops.monitor`) được khai báo từ `agentforge/ai/orchestrator_policy.py` và `model_hub.route_catalog()` — chỉ metadata thuộc source, **không chứa model ID mặc định**.
- Lưu profile và gán route **không chạy model**. Film/image routes `CONFIG_ONLY`; `ops.monitor` deterministic. Studio lấy route đã phân công từ snapshot Model Hub và kiểm tra fingerprint trước dispatch; trạng thái CONFIG_ONLY không tự cấp quyền thực thi.
- Owner có thể xóa profile chưa được tham chiếu. Muốn xóa profile đang được phân công phải bỏ gán trước. Xóa profile không xóa weights, DB khác hay workspace.
- Cơ sở dữ liệu đã tồn tại được giữ nguyên, không tự sửa hoặc migrate khi GET. Overlay/profile Owner cũ tiếp tục được đọc. Các ID route lịch sử ngoài catalog chỉ lưu trữ, không xuất hiện hay thực thi. Model trước đây chỉ tồn tại trong TOML **không tự đăng ký lại**; Owner chọn thêm khi muốn dùng.
- Các giá trị `api_key_env`, `base_url_env` của cloud profile là **tên biến môi trường**, không phải token; không có cơ chế tự nạp file `.env` ở ứng dụng. Nếu cần dùng credentials về sau, chúng phải được inject an toàn vào môi trường tiến trình. Cloud call luôn phải được duyệt, không tự fallback.
- `.env` không nằm trong Git, bị ignore để ngăn lộ bí mật. Không cần tạo file `.env` để chạy local Video Studio; không xóa `.env` sẵn có trên máy Owner bằng Git cleanup.

Chỉ ComfyUI loopback + workflow/SHA/Owner consent thuộc Film Studio mới được gửi GPU thật. Profile có mặt không chứng minh model đã tải, khả năng sinh hoặc độ phù hợp VRAM.

Xem [cấu trúc](REPOSITORY_STRUCTURE.md) và [runtime Owner](../verification/RUNTIME.md).
