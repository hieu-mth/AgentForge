# V2.6 — Website feedback loop and light UI

## What owner can do now

From **Websites → Xem website**, inspect desktop/mobile previews. In the new **Chưa ưng? Góp ý để AI sửa** section, describe specific changes (10–360 characters) and click **Yêu cầu AI chỉnh sửa**. This creates a *new version plan* using the original proposal brief + the entire new feedback. The existing proposal is never overwritten or deleted. The owner then explicitly approves the SHA and grants model usage for the new plan, just as with the original workflow.

This is a **regeneration from original brief + feedback**, not a source-aware incremental diff. It is intentionally labeled as a new draft; currently the local LLM does not receive the full previous HTML as editable context. Later product revision should use a dedicated bounded source-diff workflow with review.

If satisfied instead, **Duyệt & lưu website local** applies the original reviewed SHA. Both actions are independent. No implicit AI call, site deployment, or approval.

## UI

The app moves to a **white/light, neutral-first** visual system: white navigation, lighter page surfaces, less saturated chrome, subtle blue selected/CTA states, responsive review footer, softer shadows and hover/focus transitions. Reduced-motion preferences disable animated transitions. No new CDN/npm runtime dependencies were introduced.

**Framework decision:** This release intentionally retains the local-first vanilla JavaScript frontend. A rushed one-step migration of a 68KB multi-workflow app to React + Ant Design or Material UI would be a large regression and supply-chain change. A separately CI-tested React migration with stable API contracts and gradual route-by-route coverage is the recommended follow-on; this release does **not** claim to use React/AntD/MUI.

## Source boundaries

- \`src/agentforge/website_feedback.py\`: pure owner feedback validation & new S4 Goal planning.
- \`src/agentforge/control_center_v1.py\`: strict, authenticated, CSRF-bound revision mutation route.
- \`src/agentforge/control_center_static/app.js\`: feedback field, revision action and existing preview/approval.
- \`src/agentforge/control_center_static/app.css\`: white visual refresh and reduced motion.
- \`tests/test_website_feedback_v26.py\`: SHA/session/policy validation, full feedback retention and no model dispatch.

## Acceptance (Windows)

1. Pull main and restart Control Center; old data in \`data/\` / \`workspace/\` stays.
2. Websites → select a draft → inspect visual preview.
3. Write feedback, request revision → inspect the **new** Goal and SHA. Verify the original proposal is still selectable.
4. Explicitly approve/run model if desired; model call may take time and incur provider usage.
5. Return to Websites to compare the new draft with the original, then apply only the desired version.
6. Confirm new white navigation, responsive buttons, keyboard focus and modal close on your machine.

Never submit personal credentials, API keys or customer PII into feedback text.
