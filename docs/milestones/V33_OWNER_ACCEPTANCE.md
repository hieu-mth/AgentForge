# V3.3 — Owner acceptance and review freeze

**Scope freeze:** V2.9–V3.3 refactor and supervised operations have been implemented in reviewed PRs. After this React retention UI is merged, **stop adding features**. The owner will run local Windows acceptance and report issues, visual feedback, and business workflow gaps.

## Current architecture

```text
AgentForge/
├── ui/dashboard/                   React + Ant Design owner frontend
│   └── src/features/Retention.jsx  Reviewable local backup/restore UI
├── src/agentforge/
│   ├── ai/                         Model/worker registry, prompt intake
│   ├── core/                       Planner, runner, skill policy, task ledger
│   ├── domains/
│   │   ├── websites/               Builder, preview, feedback, AI images
│   │   ├── media/                  Rendering and video review
│   │   └── growth/                 Campaign store/report/bundle
│   ├── storage/
│   │   ├── artifact_catalog.py     Bounded inventory
│   │   └── retention.py            ZIP, SHA, quarantine, restore
│   └── control_center_v1.py        Authenticated localhost API
├── data/                           Persistent SQLite, approvals, backups
├── workspace/                      Generated products/videos (.quarantine inside)
├── tests/                          Windows regressions
└── docs/                           Architecture and milestone runbooks
```

The old flat Python module imports remain aliases to canonical modules. The original CLI remains callable; no migration of SQLite or generated products has been performed.

## Windows owner smoke-test

First stop the old Control Center using Ctrl+C, then update:

```powershell
cd D:\AgentForge
git status --short
git switch main
git pull --ff-only origin main

.\.venv\Scripts\python.exe -m unittest tests.test_paths_v29 tests.test_core_v30 tests.test_business_domains_v31 tests.test_retention_v33 tests.test_retention_api_v33 tests.test_retention_http_v33 -v

cd ui\dashboard
npm install
npm run build
cd ..\..
.\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780 --allow-external-tools
```

Visit http://127.0.0.1:8780/dashboard/ and sign in with the new console Owner code.

1. **Giao việc:** create an AI website planning Goal from a prompt, check plan and SHA, approve only when desired.
2. **Websites:** inspect desktop/mobile preview, submit a feedback revision or explicitly apply local product.
3. **Projects & AI Images:** inspect artifact inventory and, if ComfyUI is installed, view generated PNG. No image model is bundled.
4. **AI & Video Review:** inspect storyboard; check MP4 on disk before confirming; no auto-publication.
5. **Schedules, Operations, Growth & Settings:** verify real current status and deliberate owner approvals.
6. **Backups & Cleanup:** inspect one throwaway website or media run; create backup; verify ZIP; pause Operations; move exact artifact to quarantine; verify backup again; restore it. **Use test data first, not customer assets.**
7. Check that `data/company/*.sqlite3` and other products/media remain unchanged. Do not use generic recursive delete commands.

## Strict scope limits

- **Quarantine is reversible and does not save disk space.** There is no permanent-delete endpoint.
- ZIP backups are local and not encrypted; this does not replace `agentforge.ops_backup` for SQLite-consistent disaster backups.
- Model output quality, actual browser UX, ComfyUI/GPU generation, YouTube/TikTok OAuth, real customer conversion, public website hosting and bank-verified profitability require explicit real-world verification.
- A green Windows CI validates code contracts, not the owner's actual machine or business results.

## Completion criteria

Stop at V3.3 once React builds in CI and backend regression passes. Next change requests should come from owner review, not speculative scope expansion.
