# AgentForge — Local-first AI product prototyping

AgentForge is a **single-owner, supervised** Python/React application for
AI-assisted planning, task execution, artifact proposals and review.
It is not yet a production SaaS or a validated full-stack generator.

## Canonical architecture

- **Frontend:** `ui/dashboard/` (React 19, Ant Design, Vite). The old static
  Control Center frontend is removed; `/` redirects to `/dashboard/`.
- **Backend/API:** `src/agentforge/control_center_v1.py` (localhost,
  authenticated owner session, CSRF, permission gates).
- **Core:** `src/agentforge/core/` (tasks, workflow, acceptance, policy).
- **AI:** `src/agentforge/ai/`, `src/agentforge/model.py`.
- **Domains:** `src/agentforge/domains/` (websites, webapps, media, growth).
- **Contracts:** `skills/`, `workers/`, `config/`.
- **Owner data:** `data/` and `workspace/` are gitignored and **must not**
  be deleted as part of repository cleanup.

The `src/agentforge/` directory is the **current backend**, not an obsolete
source directory. Compatibility imports used by historical callers remain, but the old Python
read-only dashboard and static Owner frontend have both been removed.

## Run on Windows (PowerShell)

Requires Python 3.13+, Node/npm compatible with Vite 7:

```powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix ui/dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix ui/dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Open http://127.0.0.1:8780/dashboard/ and enter the temporary Owner code
printed in PowerShell. Use Ctrl+C to stop. Start with
`--allow-external-tools` only if you need separately approved model/network/
process capabilities. Do **not** expose the loopback server on the Internet.

If `.venv\Scripts\python.exe` is missing, run `py -0p` and recreate
the venv using the installed Python 3.13 interpreter. After setup,
rebuild the dashboard only when frontend source changes.

## Test trusted code

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd run test:navigation --prefix ui/dashboard
npm.cmd run build --prefix ui/dashboard
npm.cmd run test:browser --prefix ui/dashboard
npm.cmd ci --prefix examples/novamart --ignore-scripts
npm.cmd test --prefix examples/novamart
npm.cmd run build --prefix examples/novamart
```

**Do not run AI-generated JavaScript on the Windows host.** Docker is not
required for ordinary development, but generated React still requires an
independently verified sandbox/browser QA boundary before acceptance.
A JSX syntax PASS is not a runtime or security PASS.

## Current product limits

Static website generation uses bounded design JSON and trusted HTML.
Marketplace generation uses a fixed NovaMart reference template with an AI
catalog (demo cart, no real checkout). AI Developer can propose React source
but source revision, real-model quality and browser QA remain unverified or
unimplemented. The system separates task execution from artifact acceptance.

See [Feature Matrix](docs/audits/FEATURE_MATRIX.md),
[Full System Audit](docs/audits/FULL_SYSTEM_AUDIT.md),
[Development Roadmap](docs/audits/DEVELOPMENT_ROADMAP.md), and
[Phase 1 verification](docs/verification/phase1/README.md).

Documents under `docs/milestones/` are historical reference material,
not current startup instructions.
