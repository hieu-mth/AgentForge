# AgentForge — AI Video Studio

Nền tảng sản xuất phim AI lấy nhân vật và tài sản tái sử dụng làm trung tâm, với điều phối, dữ liệu và hậu kỳ local-first trên Windows. Chất lượng đầu ra quyết định lựa chọn model, không phải yêu cầu mọi inference đều chạy local.

Studio hỗ trợ ChatGPT Plan (OAuth), Ollama và các API cloud tương thích cho văn bản/vision; FLUX/ComfyUI cho ảnh local; LTX local và LTX Cloud cho video; FFmpeg cho hậu kỳ. Audio Director hỗ trợ WAV local, Windows SAPI, Piper, speech cloud và model nhạc/hiệu ứng đã gán. Cloud tạo ảnh và tự động gắn bộ ảnh nhận diện nhân vật chưa được tích hợp. Khả năng gọi API, chất lượng và chi phí thực tế cần Owner nghiệm thu. Owner đăng ký model, duyệt storyboard và kiểm tra thành phẩm trước khi xuất bản.

## Khởi động

Yêu cầu Python 3.13+, Node 22. Chỉ cần runtime media local nếu sản xuất bằng pipeline media hiện hành. Storyboard cloud không cần Ollama hoặc ComfyUI.

```powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media,chatgpt]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Mở http://127.0.0.1:8780/dashboard/ và đăng nhập bằng mã Owner in tại terminal. Bật `--allow-external-tools` khi chủ động tạo storyboard, gọi thử model hoặc chạy production. Quyền gọi local/cloud vẫn được kiểm tra trong Model Hub.

## Quy trình sử dụng

1. Đăng ký model và kiểm tra metadata tại Cài đặt → Model AI.
2. Phân công model cho từng năng lực ngay tại Model AI. AI điều phối chỉ quản lý quyền, công cụ và ngân sách. FFmpeg chỉ bắt buộc khi duyệt sản xuất.
3. Nhập nội dung, phương pháp sản xuất và thời lượng tại Studio video; AI chọn nhân vật từ hồ sơ đã đăng ký. Thư viện nhân vật cho phép lưu bộ ảnh nhận diện local theo phiên bản; Studio chưa tự gửi bộ ảnh đó vào pipeline tạo media.
4. Kiểm tra, chỉnh sửa storyboard; tùy chọn AI lập liên tục chuyển động và kế hoạch âm thanh; duyệt phiên bản trước khi tạo media.
5. Xem video, kiểm tra chất lượng và duyệt thành phẩm. Xuất bản là thao tác riêng.

Checkout mới không có model mặc định. Nếu nâng cấp từ Model Hub schema cũ, xem [khởi tạo lại Model Hub](docs/RUNTIME.md#khởi-tạo-lại-model-hub); ứng dụng không tự xóa DB. Không tự tải weights, cài runtime, gọi cloud hay public YouTube.

## Tài liệu

- [Kiến trúc và Model Hub](docs/ARCHITECTURE.md)
- [Phát triển và kiểm thử](docs/DEVELOPMENT.md)
- [Roadmap và trạng thái finding](docs/ROADMAP.md)
- [Runtime và vận hành](docs/RUNTIME.md)
- [Kết nối ChatGPT Plan](docs/CHATGPT.md)
- [Sản xuất video cloud](docs/CLOUD_VIDEO.md)
- [Sản xuất, QA và xuất bản](docs/PRODUCTION.md)

`data/`, `workspace/`, `models/`, `.env`, secrets và video thuộc Owner, không nằm trong source Git. CI fixture không xác nhận chất lượng video hay GPU thật.
