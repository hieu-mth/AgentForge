# C8E — Browser findings → owner-reviewed fix proposal

C8E is a **small adapter** between C8D reports and the existing C8B revision
workflow. It does not introduce another code-writing/apply mechanism.

**Important:** your latest Edge and Chrome runs for `shop-landing` reported
`PASS` with zero findings. Running C8E on those reports should return
`NO_FIX_NEEDED` and never call the model (or incur model usage charges).

## Workflow — Windows PowerShell

From `E:ProjectsAgentForge`:

```powershell
# Copy the C8D project run_id printed after browser validation.
$runId = "PASTE_C8D_PROJECT_RUN_ID"

# Purely local, READ-ONLY: no LLM, no browser, no file modifications.
.\.venv\Scripts\python.exe -m agentforge.browser_fix plan $runId
```

Possible statuses:
- `NO_FIX_NEEDED`: C8D PASS; no fix proposal or model call.
- `FIX_PROPOSAL_AVAILABLE`: C8D reported at least one recognized
  browser finding; use the command below if you want a proposed fix.
- `MANUAL_REVIEW_REQUIRED`: warning/failure lacks supported actionable
  details. Do not invent a fix; review the C8D report manually.

For a report with recognized issues **only**, explicitly authorize one model
call (which may incur cloud charges):

```powershell
.\.venv\Scripts\python.exe -m agentforge.browser_fix propose $runId --confirm-model-call
```

This creates a **C8B `PROPOSED_NOT_APPLIED` revision**, never edits products.
You must inspect, diff, quality-check and optionally run C8D on the pending
revision, then explicitly approve through the unchanged C8B apply gate:

```powershell
$revisionId = "PASTE_NEW_REVISION_ID"
.\.venv\Scripts\python.exe -m agentforge.product_revision inspect $revisionId
.\.venv\Scripts\python.exe -m agentforge.product_revision diff $revisionId
.\.venv\Scripts\python.exe -m agentforge.product_quality check-revision $revisionId
.\.venv\Scripts\python.exe -m agentforge.browser_validation revision $revisionId --confirm-browser-run --browser-channel msedge

# Only after reviewing the actual proposed HTML and test output:
.\.venv\Scripts\python.exe -m agentforge.product_revision apply $revisionId --confirm-write --sha256 PASTE_SHA_FROM_INSPECT
```

## Safety and limitations

- Accepts only C8D **project** reports stored under
  `data/company/product_builder/browser_checks/project/<slug>/<run_id>/report.json`.
  Pending C8D revision reports do not enter a second revision workflow.
- Rejects reports whose checked source SHA-256 differs from the current
  `workspace/products/<slug>/index.html`. Rerun C8D for a changed product.
- Reads only bounded report data; free-form browser error messages and page
  text are **never passed into AI prompts**. Only known issue codes, viewport
  names and validated numeric measurements are used.
- Known issue codes: `horizontal_overflow`, `javascript_errors`,
  `blocked_requests`, `capture_height`. Unsupported issues
  require manual inspection. HTML/CSS visual improvements cannot be inferred
  solely from a green test report.
- The report file is local input, not cryptographically signed evidence.
  Structural validation is not a guarantee against malicious local tampering.
- C8E does **not** invoke Playwright. It does **not** automatically retry a
  model, execute source, alter files, publish, spend or deploy.
- The resulting proposal still needs **owner approval** and exact digest match
  before C8B can create a backup and replace `index.html`.
- Unit tests use synthetic C8D reports and stubbed models; they do not
  demonstrate that a live cloud model can fix every browser defect.

## Unit tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_browser_fix.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

C8E introduces 24 unit tests on top of the 322-test C8D hotfix baseline.
Expected regression count: **346**.
