# React Dashboard — only AgentForge frontend

The Vite-built React/Ant Design Dashboard at `/dashboard/` is the canonical
Owner UI. The root `/` redirects to it; the old HTML/CSS/JS frontend was
removed. The Python backend still owns the localhost session, CSRF, API
permissions and SQLite/artifact state.

## Windows

```powershell
cd D:\AgentForge
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Open **http://127.0.0.1:8780/dashboard/**, then log in with the Owner code
printed by the server. For gated external tools, add
`--allow-external-tools`; each sensitive action still needs approval.

The optional development command is `npm.cmd run dev --prefix dashboard`
with the Python backend running. Never bind Vite or the Python server to the
public network.

- `src/App.jsx`: app shell, login, navigation and owner controls
- `src/api.js`: same-origin cookie/CSRF API client
- `src/features/`: workspace, projects, websites, review, operations, `Models.jsx` (AI Models & Routing)
- `src/components/`: shared UI and acceptance states
- `src/navigation.js`: canonical route mapping
- `src/model_hub_ui.js`: UI helper filtering capability; Python backend vẫn giữ quyền
- `tests/`: navigation, quota, permissions and acceptance tests
- `dist/`: disposable gitignored trusted build output

Do not execute generated React source in the Owner browser origin. Interactive
generated-source preview remains disabled until independently verified
isolation and QA are available.

## AI Media Studio (UI scaffold)

Open `#/media-studio` from the dedicated **AI Media Studio** sidebar item. The shell contains channel, character, production, library and model sections. It intentionally does **not** claim video rendering, character persistence or uploads are implemented. Disabled actions must remain disabled until real local APIs, approvals and end-to-end MP4 verification exist.

The existing Websites, Projects, Reviews, Models and other Owner screens remain available. No user data, artifacts or historical evidence is deleted as part of this UI cleanup. The next phase must validate image-to-video on the actual RTX 5070 before connecting render actions.

## Character Library

The independent `#/characters` screen lives as a dedicated sidebar destination and holds the intended UI for reusable character profiles, reference images, model/LoRA metadata and version history. The Character Registry now supports creating and editing metadata via authenticated Owner API backed by local SQLite (`data/characters.sqlite3` by default; configurable with `AGENTFORGE_CHARACTER_DB`). Optimistic version checks reject stale edits. Photo upload, training, generation, storyboard references and media previews are **not yet implemented**. Existing routes are preserved.

## Sidebar organization

Eight primary destinations: Tổng quan, Giao việc, AI Media Studio, Nhân vật, Sản phẩm, Kinh doanh, Đội ngũ AI, Cài đặt. Media Studio and Characters are independent; Websites, Artifacts and Reviews live in Sản phẩm; Retention/Cleanup is under Cài đặt. Legacy hash routes are unchanged.

## Owner Command Center (Tổng quan)

The overview combines the existing authenticated bootstrap snapshot (recent tasks, goals, attention, pending reviews and local video receipts). KPI counts are **sample-scoped**: bootstrap exposes at most 40 task summaries, 60 goals, 15 review items and 15 video receipts. They are not historical totals. Seven-day charts use UTC update dates from the same bounded sample, not an analytics warehouse. The health panel uses the existing authenticated `/api/film/motion` ComfyUI/GPU probe; detecting a GPU does not verify video generation. Runtime model availability and verified AI billing remain explicitly unknown. No new persistent database or automated actions are added. Run `npm run test:navigation --prefix dashboard` and `npm run build --prefix dashboard` before accepting the UI.
