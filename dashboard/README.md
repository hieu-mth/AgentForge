# Dashboard React — AgentForge Video Studio

Frontend duy nhất: React/Ant Design trong \`dashboard/src/\`, build qua Vite. Backend bảo vệ same-origin cookies, Owner login, CSRF và local-only HTTP. \`/\` redirect đến \`/dashboard/\`.

\`\`\`powershell
cd D:\AgentForge
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run test:navigation --prefix dashboard
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
\`\`\`

Các trang hiện hành: Video Studio, Character Registry, Video Projects, Model Hub, môi trường local và Publishing handoff. Không có Website/Webapp, Growth, Retention/commerce UI hoặc Goal/Skill engine. Build artifact \`dashboard/dist/\` bị Git ignore. Không tuyên bố nhận dạng nhân vật, inference hay xuất bản thực nếu chưa có Owner runtime evidence.
