# AgentForge Video Studio — Development (Windows)

Yêu cầu Python 3.13+, Node 22, FFmpeg (được cung cấp bởi optional \`[media]\`). GPU/ComfyUI, Ollama model và YouTube OAuth là các hệ thống ngoài; không tự cài hoặc gửi dữ liệu ra cloud.

\`\`\`powershell
cd D:\AgentForge
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run test:navigation --prefix dashboard
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/check_docs.py
.\.venv\Scripts\python.exe scripts/check_source_hygiene.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunContractTests
\`\`\`

Để chạy Dashboard:
\`\`\`powershell
.\.venv\Scripts\python.exe -m agentforge --port 8780
\`\`\`

Runtime certification chỉ khi Owner đồng ý:
\`\`\`powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunFFmpeg -ConfirmLocalExec -SaveReport
\`\`\`

Các luồng có tác động yêu cầu xét quyền/SHA, không tự upload. Cấm \`git clean -fdx\` và \`reset --hard\` để cleanup, vì sẽ đụng dữ liệu local. Owner có thể test GPU và continuity theo [runtime checklist](verification/RUNTIME.md). CI không thay thế Owner runtime QA.
