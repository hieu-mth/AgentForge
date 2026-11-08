# V5.3 — Developer display metadata contract

Owner reported another V5 goal stopping at the React Developer stage:

APP_CODE_CONTRACT_INVALID: Generated React metadata/fields failed validation.

## What code inspection establishes

The existing Developer validator rejected a response if the generated
title exceeded 100 characters or the summary exceeded 240 characters.
Its shared text validator emitted an APP_SPEC_INVALID ValueError, which
the task runner collapsed into APP_CODE_CONTRACT_INVALID. The full model
response is intentionally not persisted, so a screenshot cannot prove which
field failed. The failure is not proof that generated JSX was defective.

## Narrow fix

- Add title/summary length constraints directly to the model JSON schema,
  and ask for concise display metadata in the one approved Developer call.
- Normalize whitespace and trim **only** overlong title/summary, preserving
  meaningful text when possible. Keep the entire generated JSX, CSS and any
  local data files unchanged, with the previous strict validation.
- Empty/non-string title or summary still fail with redacted field-specific
  errors APP_CODE_TITLE_INVALID / APP_CODE_SUMMARY_INVALID.
- Invalid imports, unsafe APIs, malformed code, unexpected file paths, SHA
  mismatch, and existing Owner-gated source review remain blocked.
- No retries, automatic fallback, extra provider calls or auto-deployment.
  Old failed tasks remain immutable; a new Goal is required for acceptance.

## Acceptance on Windows

After merging, restart the Control Center with an up-to-date local checkout.
No Dashboard rebuild is needed for this backend-only patch.

  git pull --ff-only origin main
  .\.venv\Scripts\python.exe -m unittest tests.test_v53_developer_metadata tests.test_webapp_developer_v42b tests.test_v5_company -v

Run a **new** narrowly scoped V5 Goal using the same model profile (for
example, a local demo React catalog with search, filter and cart). Check
that Developer produces a signed source proposal; static QA is *not*
build/browser validation. Use separate reviewed offline Docker QA for
actual build/runtime checks. If the Goal still fails, record the new
redacted error code and inspect the local model/provider capacity;
the repair cannot guarantee valid application code from an 8B model.
