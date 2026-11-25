# AgentForge — Local AI Video Studio

Nền tảng sản xuất phim AI lấy nhân vật và tài sản tái sử dụng làm trung tâm, với điều phối, dữ liệu và hậu kỳ local-first trên Windows. Chất lượng đầu ra quyết định lựa chọn model, không phải yêu cầu mọi inference đều chạy local.

Source hiện hỗ trợ Ollama, FLUX/ComfyUI, LTX và FFmpeg. Cloud text hỗ trợ OpenAI-compatible và Anthropic-compatible; Reference-to-Video và cloud media chưa được tích hợp; chỉ mở rộng sau khi kiểm chứng chất lượng, khả năng gọi API và chi phí. Owner đăng ký model, duyệt storyboard và kiểm tra thành phẩm trước khi xuất bản.

## Khởi động

Yêu cầu Python 3.13+, Node 22. Chỉ cần runtime media local nếu sản xuất bằng pipeline media hiện hành. Storyboard cloud không cần Ollama hoặc ComfyUI.

```powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Mở http://127.0.0.1:8780/dashboard/ và đăng nhập bằng mã Owner in tại terminal. Bật `--allow-external-tools` khi chủ động tạo storyboard, gọi thử model hoặc chạy production. Quyền gọi local/cloud vẫn được kiểm tra trong Model Hub.

## Quy trình sử dụng

1. Đăng ký model và kiểm tra metadata tại Cài đặt → Model AI.
2. Phân công model local hoặc cloud theo năng lực, cấp quyền thực thi tương ứng tại AI điều phối. FFmpeg chỉ bắt buộc khi duyệt sản xuất.
3. Nhập nội dung và thời lượng tại Studio video; AI chọn nhân vật từ hồ sơ đã đăng ký. Hồ sơ hiện là metadata, chưa phải bộ ảnh nhận diện.
4. Kiểm tra, chỉnh sửa và duyệt storyboard trước khi tạo media.
5. Xem video, kiểm tra chất lượng và duyệt thành phẩm. Xuất bản là thao tác riêng.

Checkout mới không có model mặc định. Không tự tải weights, cài runtime, gọi cloud hay public YouTube.

## Tài liệu

- [Kiến trúc và Model Hub](docs/ARCHITECTURE.md)
- [Phát triển và kiểm thử](docs/DEVELOPMENT.md)
- [Runtime và vận hành local](docs/RUNTIME.md)
- [Sản xuất, QA và xuất bản](docs/PRODUCTION.md)

`data/`, `workspace/`, `models/`, `.env`, secrets và video thuộc Owner, không nằm trong source Git. CI fixture không xác nhận chất lượng video hay GPU thật.
