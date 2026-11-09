# React Dashboard — only AgentForge frontend

The Vite-built React/Ant Design Dashboard at `/dashboard/` is the canonical
Owner UI. The root `/` redirects to it; the old HTML/CSS/JS frontend was
removed. The Python backend still owns the localhost session, CSRF, API
permissions and SQLite/artifact state.

## Windows

```powershell
cd D:\AgentForge
npm.cmd ci --prefix ui/dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix ui/dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Open **http://127.0.0.1:8780/dashboard/**, then log in with the Owner code
printed by the server. For gated external tools, add
`--allow-external-tools`; each sensitive action still needs approval.

The optional development command is `npm.cmd run dev --prefix ui/dashboard`
with the Python backend running. Never bind Vite or the Python server to the
public network.

- `src/App.jsx`: app shell, login, navigation and owner controls
- `src/api.js`: same-origin cookie/CSRF API client
- `src/features/`: workspace, projects, websites, review, operations
- `src/components/`: shared UI and acceptance states
- `src/navigation.js`: canonical route mapping
- `tests/`: navigation, quota, permissions and acceptance tests
- `dist/`: disposable gitignored trusted build output

Do not execute generated React source in the Owner browser origin. Interactive
generated-source preview remains disabled until independently verified
isolation and QA are available.
