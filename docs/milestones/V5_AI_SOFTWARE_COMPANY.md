# AgentForge V5.0 — Bounded AI Software Company

**Status: feature implementation, CI and Owner acceptance are separate gates.**

V5 turns a single explicitly selected Goal into four **fixed, auditable**
roles. It intentionally does **not** grant arbitrary autonomous OS access.

## Functional chain

1. **Architect** (`webapp.architect`) makes one Owner-approved structured
   call and saves an immutable architecture proposal with SHA-256.
2. **Developer** (`webapp.develop`) receives that exact signed architecture
   and makes a second separately approved call to draft original local JSX/CSS.
   The trusted compiler pins React/Vite and the file allowlist. Source is not
   executed or installed.
3. **QA** (`webapp.audit`) performs deterministic *static* source/architecture
   provenance checks, returns `PASS_STATIC_ONLY` with build/browser/security
   all explicitly `false`. Zero model/process/network calls.
4. **Reviewer** (`webapp.review`) performs an independent third approved
   local model call, receives the exact signed inputs and static report, and
   produces an advisory report with missing features and risks. It can only
   recommend `REVISE` or `MANUAL_REVIEW`, **never auto-approve**.

The S4 planner uses hardcoded, type-checked output bindings; no LLM may invent
step names or dependent fields. Every source reference requires matching
immutable ID/SHA. A single Owner Run/Resume action authorizes **at most one**
model call: each subsequent model stage pauses for separate confirmation.
No retries after failure/crash, no auto cloud fallback, no persistent grants.

## How to run on Windows

1. Update local `main` and rebuild Dashboard as before.
2. In Settings, explicitly set Workspace maximum model calls to **3** if
   your local hardware/provider supports 3 planned calls. Default is 1.
3. In **Giao việc**, use the explicit prefix `AI Company V5:` with a
   functional React application request (no real checkout).
4. Approve the SHA-bound four-step Goal and review worker/model routes.
5. Run once with model permissions to authorize Architect. The Goal pauses
   again before Developer. Approve again to produce signed React source;
   static QA runs without an external process; it pauses before Reviewer.
6. Confirm Reviewer. The Goal becomes `SUCCEEDED` only when all four steps
   complete. Open **Xem kết quả công việc** to read the advisory Reviewer
   report, then **Mở mã nguồn React để Owner duyệt**.
7. Optional Docker QA requires **another** `webapp.qa` Goal and separate
   `process.run` authorization. Follow `sandbox/webapp/README.md`.
   Docker must be Linux-mode, image pinned locally and no network during QA.

A recommended input:
`AI Company V5: Tạo web app React local tên NovaMart gồm danh mục, tìm kiếm
sản phẩm hoạt động, lọc, xem chi tiết, giỏ hàng demo có tăng giảm, giao diện
mobile/desktop; dữ liệu giả, không thanh toán, không đăng nhập hay API ngoài.`

## Limits and business acceptance

- **No claim of self-operating SaaS/company:** coordination is a bounded
  workflow of 4 fixed roles, not independent agents making arbitrary plans.
- Static QA is not a React build, browser interaction test or security audit.
  Even `SUCCEEDED` means **workflow stages completed**, not app released.
- No automatic installation, hosting, browser preview of untrusted source,
  real payments, login, deployments or permissions to access other projects.
- Model may output JSX that passes static checks but does not compile or
  implement requirements correctly; the Reviewer is advisory, not authority.
- Cloud models require a configured enabled profile, explicit process-wide
  `AGENTFORGE_CLOUD_MODEL_CONSENT=YES`, Owner-approved model grants and
  credentials in environment variables; default role workers are local.
  No dollar-price estimates are asserted as billing verification.
- To prove end-to-end on an actual Windows laptop, the Owner must run
  the Goal against the configured local model and separately approve Docker
  QA. GitHub CI only exercises controlled model fixtures and build of trusted
  frontend/example code, **not** the generated application at runtime.

## Acceptance tests

`python -m unittest tests.test_role_routing_v43 tests.test_v5_company -v`

Then the repository's complete Python unittest and Windows Dashboard/Edge
workflows in GitHub CI. No merge on failing CI.

After V5, **the next valuable increment** is a dedicated source-aware React
patch workflow with true browser interaction QA in an isolated sandbox, not
unbounded autonomous model loops.
