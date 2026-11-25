# AgentForge — Local AI Video Studio

Nền tảng sản xuất video AI local-first trên Windows: Python 3.13, React/Ant Design, SQLite, Ollama, ComfyUI và FFmpeg. Owner đăng ký model, phân công năng lực, duyệt storyboard và kiểm tra thành phẩm trước khi xuất bản.

## Khởi động

Yêu cầu Python 3.13+, Node 22 và runtime media local do Owner cài đặt.

```powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Mở http://127.0.0.1:8780/dashboard/ và đăng nhập bằng mã Owner in tại terminal. Chỉ bật `--allow-external-tools` khi chủ động chạy thao tác media đã duyệt.

## Quy trình sử dụng

1. Đăng ký model và kiểm tra metadata tại Cài đặt → Model AI.
2. Phân công model local theo năng lực, cấp quyền thực thi và FFmpeg tại AI điều phối.
3. Nhập nội dung, chọn nhân vật và thời lượng tại Studio video.
4. Kiểm tra, chỉnh sửa và duyệt storyboard trước khi tạo media.
5. Xem video, kiểm tra chất lượng và duyệt thành phẩm. Xuất bản là thao tác riêng.

Checkout mới không có model mặc định. Không tự tải weights, cài runtime, gọi cloud hay public YouTube.

## Tài liệu

- [Kiến trúc và Model Hub](docs/ARCHITECTURE.md)
- [Phát triển và kiểm thử](docs/DEVELOPMENT.md)
- [Runtime và vận hành local](docs/RUNTIME.md)
- [Sản xuất, QA và xuất bản](docs/PRODUCTION.md)

`data/`, `workspace/`, `models/`, `.env`, secrets và video thuộc Owner, không nằm trong source Git. CI fixture không xác nhận chất lượng video hay GPU thật.
