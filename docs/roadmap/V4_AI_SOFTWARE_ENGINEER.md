# AgentForge V4 — AI Software Engineer, incremental delivery

Updated: 2026-11-07. Owner goal: real interactive web applications, not another
landing page that resembles an ecommerce site.

## Non-negotiable architecture

- Keep Python/SQLite/Goal/Task/worker authority, Windows local-first and
  existing V3.6 website flow. Do **not** rewrite the dashboard.
- No untrusted model-authored executable code on the host. Running arbitrary
  generated JavaScript, dependencies and build scripts must eventually happen
  only in a verified sandbox with separate \`process.run\` consent.
- All model outputs are untrusted and immutable until approved. Keep Goal SHA,
  model call limits, proposal SHA, owner confirmation and no silent retries.
- Never connect to payment gateways, publish, impersonate real brands, collect
  identities or claim demo product prices are real.
- Ship independent PRs/commits; CI must pass before merge. Test on actual
  Windows/Ollama separately before labeling an AI flow production ready.

## Milestones

| Milestone | Deliverables | Exit criteria |
| --- | --- | --- |
| V4.0a — Interactive reference | Standalone Vite + React NovaMart with searchable catalogue, category filters, sort, product details, working client-side cart, mobile layout and tests | \`npm ci && npm test && npm run build\` succeeds, browser flows work, no backend/CDN/payment |
| V4.0b — Owner-gated webapp proposals | New \`webapp.create\` skill and \`webapp.draft\` Goal, model-controlled typed ecommerce data/spec, audited React source renderer, SHA-bound read/apply, no code execution | Planner → permission gate → one model call → immutable source proposal; safe paths and source validation; isolated tests |
| V4.1 — Revision and versioning | Source-aware app revision with patch/diff view, project version records, changed-file scoped reviews | Edit a single feature without losing unrelated parts, SHA prevents stale apply |
| V4.2 — Sandboxed build and QA | Explicitly configured pinned offline Docker build/test, no host secrets/network, separate Owner approval; browser screenshots remain future work | Fail closed when Docker or local image unavailable; QA may run only after process.run consent |
| V4.3 — Multi-model routing | User-selectable local/cloud worker model profiles with costs and caps | Predictable cost ceiling and no provider changes without permission |
| V5.0 — Multi-agent product loop | Architect, Designer, Developer, QA and Reviewer skill orchestration around the same versioned artifact | Demonstrated 3-step real-app edit flow with gated execution and reproducible tests |

## Current baseline

V3.6 \`web.create\` generates standalone offline HTML using constrained
AI-selected design elements. It cannot implement state, routing, product
search, functional filters or a cart. Avoid misrepresenting the V4.0a reference
demo as an AI-generated application: it is a **hand-reviewed golden sample**
for functional acceptance and the starting point for the V4.0b compiler.

## Functional acceptance for NovaMart

- Search actually reduces visible products, with visible empty state.
- Category selection and price sort behave deterministically.
- Product details are accessible from a card without navigation to another host.
- Cart add, remove, quantity +/- and subtotal update correctly and never go
  negative; no checkout or payment is performed.
- The app works with airplane mode after dependencies are installed and built.
- Desktop and mobile layouts have no deliberate horizontal overflow.
- A future generated app must pass the same tests as the reference.

## Deployment and boundary

V4.0a is a source-only demo in \`examples/novamart/\`. It does not execute
inside AgentForge's authenticated server and does not receive credentials.
To run, an Owner manually starts Vite in a separate terminal, only after
reviewing code and choosing to install dependencies. V4.0b proposal generation
must remain unexecuted until a reviewed, isolated build runner is available.

## V4.2 implementation note

The optional Docker-based runner tests a signed React proposal in an isolated
Linux container. It never auto-installs Docker, fetches an image or runs npm
on the host. The Owner must prepare a local image and pin its sha256 ID;
otherwise `SANDBOX_UNAVAILABLE` is returned without executing generated code.
This is an integration harness, **not** proof of complete sandbox security and
not a browser automation or code-generation feature. Instructions live in
`sandbox/webapp/README.md`.
