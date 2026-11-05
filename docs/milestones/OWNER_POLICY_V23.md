# V2.3 — Owner workspace policy (roles and estimated call budgets)

This milestone separates **prompt-workspace restrictions** from background Autopilot quota and external provider billing. It does **not** give role profiles new permissions or claim to enforce actual VND spend.

## Dashboard flow

On **Settings**, configure:

- Maximum **estimated model calls per new prompt Goal**: integer 0..3. The current prompt UI creates website/storyboard Goals with estimate 1.
- Enable/disable **Website Builder** intake.
- Enable/disable **Storyboard** intake.

Changing settings requires an authenticated owner session, same-origin CSRF, exact ack and bounded fields. The policy is stored in \`data/company/workspace_policy.sqlite3\` with an append-only change history. No API credentials, customer contacts or billing transactions are stored in this policy table.

The **Giao việc** screen shows the current prompt limits and is denied server-side if the selected workflow is disabled or its estimated model count exceeds the owner cap.

This policy only restricts **new Goals created through the prompt-first dashboard endpoint**. It does not retroactively revoke an approved/ongoing Goal, does not change S4/CLI rights or V1.3 Autopilot policy and **does not cap provider invoices**. Such controls remain under distinct owner approvals and provider account settings. To pause new skill execution generally, use existing **PAUSE_OPERATIONS**.

## Source structure

- \`src/agentforge/workspace_policy.py\`: isolated local policy store and audit history.
- \`src/agentforge/prompt_intake.py\`: planner checks current policy before creating a new Goal.
- \`src/agentforge/control_center_v1.py\`: authenticated POST action to save policy; read-only summary for UI.
- \`src/agentforge/control_center_static/app.js\`: Settings controls; no client-authorized role elevation.
- \`tests/test_workspace_policy_v23.py\`: coercion, audit, permission and policy enforcement regressions.

## No-risk migration

Existing \`data/\`, \`workspace/\`, tasks, proposals and media outputs are untouched. When no policy file exists, a conservative default allows 1 estimated model call and the two existing prompt types, but **still requires owner SHA approval and execution grants**. The first policy update creates its SQLite file. No cleanup or schema migration of other stores is performed.

## Acceptance

1. Open Settings and set model calls per new Goal to 0.
2. Try creating a new landing page Goal through Giao việc: denied with a controlled policy message; no model call.
3. Restore cap to 1, enable Website, create a new prompt Goal: PLANNED only.
4. Inspect SHA and grant required model/workspace permissions separately to run.
5. Check historical tasks and artifacts remain intact, and actual provider spending is still marked unverified.
