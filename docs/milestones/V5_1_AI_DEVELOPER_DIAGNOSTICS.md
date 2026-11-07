# V5.1 — AI Developer failure triage and V5 intent recognition

Owner screenshot: `webapp.develop` failed with an overly generic
`APP_CODE_FAILED` and no usable reason, while a brief requesting all four
V5 roles had fallen into single-role Developer intake.

## Changes
- Recognize **all four explicitly named roles**
  (`AI Architect`, `AI Developer`, `QA`, `AI Reviewer`) as V5 even when
  the Owner does not type the exact English `AI Company V5:` prefix. The
  planning UI supplies the correct 3-call *plan limit*. The 3-call Owner
  workspace cap still needs to be enabled in Settings. No model is called
  when a plan is created.
- Raise structured-cloud **React JSON** output allowance from 4096 to
  8192 tokens for the dedicated Developer worker only. Other worker/model
  limits remain unchanged. One Owner-confirmed model request, no retries.
- Map the known trusted adapter failures to fixed redacted error codes:
  `MODEL_OUTPUT_LIMIT`, `MODEL_EMPTY_OUTPUT`,
  `APP_CODE_JSON_INVALID`, `APP_CODE_CONTRACT_INVALID`,
  `MODEL_CONFIG_INVALID`, `MODEL_PERMISSION_DENIED`,
  `APP_LOCAL_IO_FAILED`, etc. Never persist raw model responses, URLs,
  tokens or exception bodies.
- New tests ensure no secret leakage, correct model output token budget,
  and correct V5 Goal routing for a natural Vietnamese four-role brief.

## How to diagnose on Windows

1. Stop Control Center, `git pull --ff-only origin main`, rebuild UI.
2. In Settings set Workspace cap to **3 model calls** for V5. Verify your
   chosen Ollama model is installed/running or the explicitly opted-in
   cloud profile works.
3. Submit a **new** Goal with `AI Company V5:` or clearly name all four
   roles. Existing failed Goals remain immutable and are **not replayed**.
4. Approve each model stage individually. If model output fails, the new
   stable error code helps distinguish output-token exhaustion from schema
   validation, model connectivity, local IO and configuration.
5. After source generation, use the already available separate Owner
   Docker QA approval flow. Static QA success is not runtime QA.

**Limitations:** The original screenshot alone cannot reveal the underlying
exception because old releases intentionally stored only the generic
redacted error; code changes cannot retroactively restore that raw error.
Increasing a cloud output cap does not guarantee an 8B local Ollama model
will produce valid complex React JSON. Actual Ollama and Docker tests require
the Owner's Windows machine and are not covered by CI fixtures.
