# Repository cleanup — legacy UI retirement

Baseline: main `446387c10b6ce913b5833f16e45d745e8a5c482a`
(November 9, 2026). Work branch:
`refactor/remove-legacy-ui-20261109` (PR #59).

## Removed

- `src/agentforge/control_center_static/{app.html,app.js,app.css}`:
  deprecated second Owner UI
- `src/agentforge/dashboard_v0.py`: deprecated Python HTML dashboard
  and unauthenticated read-only listener
- `ai/README.md`: misleading repository-root AI placeholder; real code
  remains under `src/agentforge/ai/`
- Three Node tests exclusively targeting removed static `app.js`
- Legacy routes `/app.js`, `/app.css`, `/app.html`; all now return 404
- The legacy frontend's setuptools package-data and CI steps

## Replaced rather than deleted

- `/` now redirects to `/dashboard/`; React is the only Owner frontend.
- The Python server and its authenticated JSON APIs remain intact.
- Task/result public serialization moved to
  `src/agentforge/core/public_serialization.py`, including bounded
  artifact basenames and request-redaction behavior.
- Python V0-only dashboard tests were replaced by tests for canonical
  authenticated API and trusted analytics/growth services. Additional
  serialization tests cover redaction, path exposure, recursion depth and
  screenshot count.
- `python -m agentforge` now starts the canonical dashboard; the historical
  workflow module remains available when invoked explicitly.
- Setup READMEs and architecture references now describe one frontend and
  current Windows/npm-ci commands.

## Intentionally retained

- `src/agentforge/`: production Python package. **Never delete this folder.**
- `src/agentforge/core/`, `domains/`, `ai/`, `storage/`: live canonical
  implementations.
- Small compatibility import aliases: exercised by architecture tests,
  monkeypatch contracts or historical CLI callers; removing them without
  explicit migration would be unsafe.
- `examples/novamart/`: reference template consumed by Marketplace Builder.
- `skills/`, `workers/`, `config/`: actual workflow/permission contracts.
- `docs/milestones/`: historical evidence and links, clearly labeled as
  historical rather than current instructions.
- `data/`, `workspace/`, user backups, secrets and generated artifacts:
  untouched and never eligible for repository cleanup.

## Verification contract

GitHub Actions on Windows runs Python/JS tests, React and NovaMart builds,
Edge smokes, and the read-only PowerShell acceptance script. Check PR #59
for the latest independent results; do not infer PASS from a source edit.
No AI inference or untrusted generated code is executed by this cleanup.
Docker isolation/browser QA for generated React remains UNVERIFIED.

## Developer sync

Once this branch is merged and CI is green, on Windows:

```powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main
npm.cmd ci --prefix ui/dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix ui/dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

If `.venv` was removed locally, recreate it using Python 3.13 as described
in the repository README. Never use `git clean -fdx` on a machine holding
Owner data.
