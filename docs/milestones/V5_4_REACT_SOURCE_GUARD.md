# V5.4 — React source guard precision and actionable diagnostics

## Observed

An Owner V5 Goal failed in the Developer step with
\`APP_CODE_UNSAFE: Generated code includes blocked remote/active patterns.\`
The error proves only that the static source validator matched a forbidden
pattern. The generated source is not stored on this failure, so the screenshot
does **not** establish which exact pattern caused the incident.

Review identified a concrete false positive: an inline SVG tag commonly uses
\`xmlns="http://www.w3.org/2000/svg"\` (and occasionally
\`xmlnsXlink="http://www.w3.org/1999/xlink"\`). Those are static XML
namespace identifiers, not remote resources, but the prior regex rejected
every occurrence of \`http://\`. The previous regex also matched component
names such as \`<BaseBadge>\` as an embedded \`<base>\` HTML tag.

## Changes

- Ignore exactly those two standard namespace values **only when used as
  JSX namespace attributes** during static screening. Preserve the original
  source bytes, the Owner SHA/proposal lifecycle, and every other deny rule.
- Require a word boundary when matching blocked HTML tag names; custom
  React components such as \`<ScriptLabel>\` are not \`<script>\` tags.
- Report stable redacted classes for remote URLs, browser/runtime APIs,
  dynamic imports/evaluation, embedded HTML, CSS asset loading and invalid
  source imports. Do not persist code snippets, model output, matched
  URLs, rejected filenames or credentials.
- Tell Developer to use CSS gradients, static inline SVG paths and fictitious
  local data rather than live images, external URLs or \`url()\` CSS.
- Preserve one Owner-approved inference call, the SHA-bound proposal, static
  QA/report semantics, separate Docker/browser QA and all previous permissions.
  No retries or model fallback.

## Acceptance and limitations

Tests confirm that standards-compliant SVG namespace attributes pass while
external image URLs, even with the same namespace URL in an \`href\` rather
than \`xmlns\`, remain blocked. Unsafe JS APIs/imports/CSS and attempts to
embed forbidden HTML tags still fail. Source validation is only a conservative
screen; it does not replace an AST-based JS audit or real browser sandbox.
Actual local model behavior must still be assessed on the Owner machine.

After merging:

\`\`\`powershell
cd D:\AgentForge
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m unittest tests.test_v54_developer_safety_diagnostics tests.test_webapp_developer_v42b tests.test_v5_company -v
\`\`\`

Restart Control Center from the updated checkout. Submit a **new** narrowly
scoped V5 demo Goal and approve each model step individually. Failed Goals
remain immutable. If another rule is blocked, the new redacted category
provides a reason to refine the next request, but does not prove an unsafe
operation occurred at runtime or warrant disabling safety checks.
