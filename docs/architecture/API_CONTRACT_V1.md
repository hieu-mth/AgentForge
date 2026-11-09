# AgentForge Base V1 — M0: API contract baseline

**Baseline:** `main` commit `b4dac8b` (09/11/2026). **M0 freezes behavior, not current file layout.** Backend is a local-first single-Owner Python HTTP application; all consumers and existing CLI names must remain compatible during M3.

## API lifecycle and security invariants

| Boundary | Contract to preserve |
| --- | --- |
| Bind | IPv4 `127.0.0.1` only; not a public API or multi-tenant server |
| Entry | `python -m agentforge --port 8780`, `create_server(...)`; legacy `agentforge.control_center_v1` import/CLI |
| Dashboard | Root `/` redirects `/dashboard/`; only reviewed `dashboard/dist` assets are served |
| Owner login | `POST /api/login`, code supplied at launch; in-memory HttpOnly SameSite=Strict cookie, 8-hour session |
| Login protection | Failed attempts limited, host/origin and Sec-Fetch-Site validated, no credential logging |
| Auth | All `/api/*` GETs besides login (POST only) require an authenticated session |
| Mutations | JSON Content-Type and bounded request body; same Origin, session + per-session CSRF, explicit per-action ack and lower-level policy gate |
| Privileged actions | No network, paid model or process call by default. Owner consent and per-task permission grants remain mandatory |
| Content | Strict CSP, `nosniff`, no CORS, isolated preview with scripts disabled |
| Failures | Unauthenticated GET returns 401; bad origin/CSRF or credentials return 403/401; invalid owner mutation remains 400; unsupported methods return 405 |
| Persistence | All existing SQLite, SHA, review markers, `data/` and `workspace/` paths must remain unchanged |
| Retries | No automatic retry of uncertain external actions; no silently accepted artifacts |

## Endpoint groups (existing, not new functionality)

| Group | Authenticated GET | Owner-controlled POST |
| --- | --- | --- |
| Session / dashboard | `/api/session`, `/api/bootstrap` | `/api/login`, `/api/logout` |
| Tasks / plans | `/api/tasks/{id}`, `/api/goals/{id}`, `/api/memory` | `/api/goals/*`, `/api/schedules/*`, `/api/memory/set`, `/api/workspace/*` |
| Website / WebApp | `/api/proposals/{id}`, `/api/proposals/{id}/preview`, `/api/webapps/{id}` | `/api/proposals/*`, `/api/webapps/*`, `/api/artifacts/*` |
| Media / review | `/api/videos/{id}`, `/api/drafts/{id}`, `/api/image/*` | `/api/videos/*`, `/api/drafts/*`, `/api/media/prepare`, `/api/image/*` |
| Operations | `/api/model/health`, `/api/ops/health`, `/api/retention/*`, `/api/artifacts`, `/api/growth/{id}` | `/api/ops/control`, `/api/retention/*`, `/api/campaigns/*`, `/api/autopilot/configure` |

These are **route families**, not new generic wildcard permissions. Concrete routes retain their per-handler checks. Unknown GET resources remain 404 and unknown owner mutations remain 400 with `ValueError`. Do **not** infer a new API or change response schemas from this document.

## Intended M3 boundaries

```text
agentforge/__main__.py
    -> agentforge/api/server.py         # HTTP transport, security headers, JSON, URLs
         -> api/auth.py                  # login/cookie/session only
         -> api/static.py                # trusted React build assets only
         -> api/routes/read.py           # authenticated read routes
         -> api/routes/mutations.py      # owner actions, per-feature guards
         -> api/routes/bootstrap.py      # bootstrap presentation/aggregation
    -> agentforge/core + domains         # business logic untouched in M3

agentforge/control_center_v1.py         # backwards-compatible import + CLI facade
```

M3 must **not** implement a new HTTP framework, alter task semantics or modify any `domains/*` logic. M6 model routing, M7 dashboard model management and M8 skill dispatch belong to later releases.

## Release verification

- Preserve all current Windows CI steps and add `tests/test_m3_api_boundaries.py`.
- Test real localhost owner login, unauthenticated read, invalid CSRF, logout and strict Host/Origin on HTTP.
- Check source import boundaries using Python AST (no Core/domain import of `agentforge.api`).
- Keep `agentforge.control_center_v1.create_server` and `_owner_action` public compatibility aliases.
- No migration of existing Owner data; no GPU/API spend; no generated JS execution.
- Owner merges to `main` only after Windows CI PASS.

Source layout and migration progress: [current structure](REPOSITORY_STRUCTURE.md), [migration plan](MIGRATION_PLAN.md), [target](TARGET_STRUCTURE.md).
