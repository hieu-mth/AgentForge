# AgentForge UI

The **React 19 + Ant Design 6 dashboard** in `ui/dashboard/` is the only frontend.
Python's authenticated loopback Control Center serves its Vite production build at
`http://127.0.0.1:8780/dashboard/`; requests to `/` redirect there.

Build on Windows from the repository root:

```powershell
npm.cmd ci --prefix ui/dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix ui/dashboard
```

Start the Python server using your installed environment:

```powershell
py -3.13 -m agentforge.control_center_v1 --port 8780
```

The deprecated static Control Center (root HTML/CSS/JS) was removed. The
React dashboard still calls the existing authenticated JSON APIs; this is a
local-owner tool and must not be exposed publicly.
