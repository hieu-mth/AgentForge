# AgentForge React Dashboard

React 19 + Ant Design 6 + Vite 7. This is a **separate frontend application**,
not a replacement for the Python runtime or SQLite databases. No CDN, public
dashboard hosting or separate user authentication is introduced.

## One-time build on Windows PowerShell

Install Node.js 22 (or a version supported by this Vite release), then:

    cd D:\AgentForge
    git pull --ff-only origin main
    cd ui\dashboard
    npm install
    npm run build
    cd ..\..
    .\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780 --allow-external-tools

Browse:

- **New React UI**: http://127.0.0.1:8780/dashboard/
- **Legacy fallback**: http://127.0.0.1:8780/

Both use the same Python session, Owner code, CSRF, Goal/Task records, and SHA
approval gates. The built files live in \`ui/dashboard/dist/\` and are gitignored.
A Python code update does not automatically install npm packages or rebuild
React assets; run \`npm run build\` after pulling UI changes.

## Development mode (optional)

Keep the Python backend running at 127.0.0.1:8780 and run, in a second terminal:

    cd D:\AgentForge\ui\dashboard
    npm run dev

Open http://127.0.0.1:5173/dashboard/. The Vite local proxy routes \`/api\`
calls to the Python backend. **Do not bind Vite to 0.0.0.0** or expose the
local Owner session to LAN/Public Internet.

## Structure

\`\`\`
ui/dashboard/
├── index.html
├── package.json
├── vite.config.js
├── src/
│   ├── App.jsx          Shell, authentication, API mutations, navigation
│   ├── api.js           Cookie/CSRF same-origin client, no tokens in storage
│   ├── components/
│   │   └── shared.jsx  Status badges and presentation helpers
│   ├── features/
│   │   ├── Workspace.jsx  Prompt, plan and owner permission review
│   │   ├── Websites.jsx   Website preview, feedback and SHA approval
│   │   └── Operations.jsx  Overview, finance and read-only views
│   ├── main.jsx        Ant Design theme + React root
│   └── styles.css      Light responsive design system
└── dist/               Generated only, gitignored
\`\`\`

The frontend is not allowed to authorize unrestricted skills. Approval,
workflow permissions and financial restrictions remain server-side.

## Current screens

- **Giao việc**: natural-language intake; create and inspect a supervised plan
- **Goals**: SHA approval, run/resume with explicit permission grants
- **Tasks**: inspect task status and audit logs
- **Websites**: desktop/mobile sandbox preview, SHA source, feedback revision
  request, and explicit local apply
- **Tổng quan**: status from existing V2 pilot
- **Team / Channels / Finance / Settings**: read-only, sourced from existing
  API records, do not fabricate OAuth or provider costs
- **Projects & Files**: route back to original owner console for now

Advanced workflow screens still live at the legacy \`/\` URL; migrating them
will be separate focused PRs. It is intentional that this first React slice
does not claim parity with all 24 legacy skills.

## Security

- HTTP server binds **127.0.0.1** and serves Vite-built static files only.
- \`/api/*\` requires the same HttpOnly owner cookie/CSRF as the legacy UI.
- Untrusted AI-produced website preview is rendered in an iframe with
  \`sandbox=""\`, no script/same-origin access; it is not a deployed website.
- React app cannot read Owner code from any saved browser storage.
- \`ui/dashboard/dist/\` is safe to regenerate; \`data/\` and \`workspace/\`
  are not build caches and must never be deleted as part of an upgrade.

## Acceptance

Windows CI builds the React app and runs Python static route tests.
End-user validation is still required on the local Windows machine for modal
interaction, responsive layout, actual preview output and real model calls.


## V3.2–V3.3 native owner workflows

Native React now includes Projects & local AI Image Studio (including a
SHA-verified PNG preview), AI Draft/Video owner review, Schedules, Operations,
Intelligence, Growth, Settings, Owner Memory and Backups & Retention. All
writes use the existing authenticated Python API with explicit owner
confirmations. The React header also supports Owner logout.

In **Backups & Retention**:
1. Inspect one applied website or media run to bind its tree SHA to the
   current owner session.
2. Create its local ZIP snapshot, leaving the live source untouched.
3. Explicitly verify ZIP and per-file SHA in this owner session.
4. Pause Operations before any quarantine/restore.
5. Confirm reversible quarantine or non-overwriting restore.
6. There is deliberately **no permanent-delete button**.

These screens do not establish OAuth or public site deployment. The legacy
control panel stays at `/` only as a diagnostic/fallback path pending
hands-on acceptance; it is not another data store.
