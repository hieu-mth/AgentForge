# AgentForge Video Studio — Development (Windows)

Yêu cầu Python 3.13+, Node 22, FFmpeg (được cung cấp bởi optional `[media]`). GPU/ComfyUI, Ollama model và YouTube OAuth là các hệ thống ngoài; không tự cài hoặc gửi dữ liệu ra cloud.

```powershell
cd D:\AgentForge
.\.venv\Scripts\python.exe -m pip install -e ".[media,chatgpt]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run test:navigation --prefix dashboard
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/check_docs.py
.\.venv\Scripts\python.exe scripts/check_source_hygiene.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunContractTests
```

`draft_resources.require_gpu()` kiểm tra RAM, Windows commit và VRAM trước khi gửi job.
Trong lúc chạy motion, worker chỉ đọc RAM và Windows commit để quyết định có cần ngắt.
Nếu không xác nhận được lệnh ngắt, production chuyển sang **Cần đối soát** và giữ attempt hiện tại.
Lần chạy mới phải được Owner xác nhận cho đúng checkpoint đã kết thúc lỗi.

Script `scripts/setup_windows.ps1 -Install -AllowNetwork` cài cùng extras `[media,chatgpt]` như README và CI; không cài `[youtube]` mặc định. Không có quyền mạng nếu thiếu consent.

Để chạy Dashboard:
```powershell
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Runtime certification chỉ khi Owner đồng ý:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunFFmpeg -ConfirmLocalExec -SaveReport
```

Các luồng có tác động yêu cầu xét quyền/SHA, không tự upload. Cấm `git clean -fdx` và `reset --hard` để cleanup, vì sẽ đụng dữ liệu local. Owner có thể test GPU và continuity theo [runtime checklist](RUNTIME.md). CI không thay thế Owner runtime QA.

Frontend Edge smoke: `npm.cmd run test:browser --prefix dashboard` sau khi build và cài Microsoft Edge. Kết quả nghiệm thu dùng CI cùng commit; fixture không gọi model thật.

## Kiểm tra source và build

CI cài Ruff riêng trên runner, không phải runtime dependency. Gate F821/F822/F823 chặn tên không xác định; inventory F401/F841 chưa chặn CI để review re-export và test seam. Knip dùng entry production/build/test trong `dashboard/knip.json`, báo các file, export và dependency nghi dư thừa; không tự xóa theo kết quả scan. Review từng finding trước khi chốt.

```powershell
python -m pip install ruff==0.11.13
python -m ruff check agentforge scripts tests --select F821,F822,F823
python -m ruff check agentforge scripts tests --select F401,F841
cd dashboard
npm exec --yes --package=knip@5.46.0 -- knip
npm run build
node tests/build-layout.mjs
```

Gate build kiểm tra 8 màn hình tải theo nhu cầu và tổng JS thuộc initial graph nhỏ hơn baseline 1.355.410 bytes. Manifest là build artifact, không được serve bởi API static. Chưa suy ra tốc độ runtime thực tế từ kích thước bundle.
