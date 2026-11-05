# Website preview-first UX (V2.5)

## Motivation

Owner should not have to read HTML/CSS to assess a landing page. Source is a secondary advanced disclosure; visual rendering comes before approval.

## Dashboard

1. Navigate to **Websites** and select an existing un-applied proposal.
2. Click **Xem website**. A real rendered page appears immediately below with **Desktop** and **Mobile** viewport options.
3. Scroll the contained preview to inspect copy/layout/fonts. All scripts, forms, networking and external content are disabled. Links and forms in the sandbox are **not evidence** of production CTA behavior.
4. Open **Xem mã nguồn & SHA (nâng cao)** only if needed. When satisfied, explicitly choose **Duyệt & lưu website local**; this rechecks the digest and static quality gate before writing.
5. After applying, manually open \`workspace/products/SLUG/index.html\` in a real local browser for functional acceptance. Approval does not publish the website online.

## Threat model

\`GET /api/proposals/{id}/preview\` is an authenticated read-only endpoint. It retrieves the existing persisted proposal using Product Builder's digest-verifying reader. It does not create a new model call, apply, generate files or deploy.

The preview response uses a **separate** Content Security Policy with the \`sandbox\` directive and \`script-src 'none'; connect-src 'none'; form-action 'none'; default-src 'none'; img-src data:\`, and can be framed **only** by the same local Control Center. The enclosing iframe also has \`sandbox=""\` and no referrer. There is no allow-scripts or allow-same-origin option. Normal Control Center pages retain their stricter baseline CSP and \`X-Frame-Options: DENY\`.

This is safe *visual inspection*, not permission to execute untrusted website source. External assets won't load, and interactivity can't be validated inside the isolated preview.

## Limitations / acceptance

- AI text model may still produce a visually weak design; rendering alone does not guarantee beauty.
- The preview uses its own local viewport; use a real mobile browser before shipping.
- Proposed JS is intentionally disabled; interactive CTA and navigation need real local browser testing after approval.
- Image assets generated later by ComfyUI live only inside the applied project. This pre-apply preview shows self-contained proposal markup and styles, not subsequent image attachments.
- Proposal/source SHA comparison and manual owner approval remain mandatory.

## Files

- \`src/agentforge/website_preview.py\`: validated digest-aware proposal-to-preview renderer.
- \`src/agentforge/control_center_v1.py\`: authenticated read-only isolated HTML endpoint.
- \`src/agentforge/control_center_static/app.js\`, \`app.css\`: visual tabs and responsive frame, advanced-only source.
- \`tests/test_website_visual_preview.py\`: real localhost auth/CSP/digest/no-apply regression.
