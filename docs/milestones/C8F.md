# C8F — Bounded local Build → Test → Propose Fix workflow

**C8F completes the static Web Builder MVP** as a small checkpointed workflow
over existing C8A/B/C/D/E modules. Its purpose is **coordination**, not a new
agent that can freely run code or deploy. Only one attempt of each operation is
allowed per cycle:

1. Build a product with C8A (or use an existing product).
2. Start a C8F cycle; attach a prior C8D report or explicitly run one browser
   baseline check.
3. If C8D says PASS, stop automatically at `NO_FIX_NEEDED` with **no AI call**.
4. If a known browser issue exists, the owner can approve **one** C8E model
   attempt, producing an un-applied C8B proposal.
5. The owner can approve **one** C8D browser check on the proposed revision.
6. Review HTML, diff, screenshots and C8B's SHA-256, then **apply manually
   through the separate C8B command**, or reject it. No automatic apply.

No scheduler, no hidden background execution, no auto-retries. C8F writes
immutable JSON checkpoints to ignored local `data/` and can be inspected
after closing/restarting the terminal. A failed attempt remains spent for that
cycle; create a new cycle if you intentionally want another run.

## Quick acceptance test using an existing PASS report

The user's Edge and Chrome C8D reports already passed. Do **not** spend money
calling AI to fix a page that the supported checks consider clean.

```powershell
cd E:\Projects\AgentForge
git pull --ff-only origin main

# Reuse an existing project report without launching Edge or calling AI.
.\.venv\Scripts\python.exe -m agentforge.product_cycle start shop-landing --report-run-id 2c6ef3dca9454cde92980d91ba518d8a

# Copy the returned cycle_id and inspect the persistent checkpoint.
$cycleId = "PASTE_CYCLE_ID"
.\.venv\Scripts\python.exe -m agentforge.product_cycle inspect $cycleId
```

Expected: `status: NO_FIX_NEEDED`, same baseline project and browser run,
no generated revision, no spend, no modification to the product.

## New browser run for an existing product

```powershell
.\.venv\Scripts\python.exe -m agentforge.product_cycle start shop-landing
$cycleId = "PASTE_NEW_CYCLE_ID"

# Owner explicitly authorizes real browser execution.
.\.venv\Scripts\python.exe -m agentforge.product_cycle test $cycleId --confirm-browser-run --browser-channel msedge

.\.venv\Scripts\python.exe -m agentforge.product_cycle inspect $cycleId
```

With Chromium/Edge already installed and Playwright installed, `test` delegates
to C8D. JavaScript in the generated HTML **does execute**. The ephemeral
browser context and intercepted HTTP routes are **not** an OS/network security
sandbox. Inspect the source first and run as a low-privilege user.

## If the baseline report found fixable issues

```powershell
# No model call occurs unless BOTH an issue and this flag are present:
.\.venv\Scripts\python.exe -m agentforge.product_cycle propose $cycleId --confirm-model-call

# Inspect the revision_id from the output, review the complete HTML and diff.
$revisionId = "PASTE_REVISION_ID"
.\.venv\Scripts\python.exe -m agentforge.product_revision inspect $revisionId
.\.venv\Scripts\python.exe -m agentforge.product_revision diff $revisionId
.\.venv\Scripts\python.exe -m agentforge.product_quality check-revision $revisionId

# Preview and check candidate; still does not apply it:
.\.venv\Scripts\python.exe -m agentforge.product_cycle test-revision $cycleId --confirm-browser-run --browser-channel msedge

# C8F reports READY_FOR_OWNER_REVIEW, CANDIDATE_FAILED, or
# CANDIDATE_WARN_REVIEW_REQUIRED. Inspect candidate screenshots.
.\.venv\Scripts\python.exe -m agentforge.product_cycle inspect $cycleId

# Only after consciously approving the code/review:
.\.venv\Scripts\python.exe -m agentforge.product_revision apply $revisionId --confirm-write --sha256 PASTE_SHA256_FROM_C8B_INSPECT
```

The final `apply` command belongs to C8B, not C8F. It makes a verified
backup of the original HTML. C8F does not claim quality automatically
because a browser test returned PASS: a human still reviews screenshots and
product behavior.

## States

| Status | Meaning |
|---|---|
| `AWAITING_BROWSER_TEST` | Started, no baseline report yet |
| `NO_FIX_NEEDED` | Baseline PASS; no AI spending |
| `FIX_PROPOSAL_AVAILABLE` | Supported C8D issues, optional one model call |
| `MANUAL_REVIEW_REQUIRED` | Unsupported or ambiguous browser findings |
| `AWAITING_CANDIDATE_BROWSER_TEST` | A C8B proposal exists, still unapplied |
| `READY_FOR_OWNER_REVIEW` | Candidate browser PASS, still unapplied |
| `CANDIDATE_FAILED` | Candidate browser found failures; don't auto-apply |
| `CANDIDATE_WARN_REVIEW_REQUIRED` | Candidate had warnings |
| `APPLIED_VIA_C8B` | The owner separately applied the C8B proposal |
| `STALE_CYCLE` | Current project differs from checkpoint |
| `*_ATTEMPT_INTERRUPTED` | External step started but has no completed result |

## Limits and implementation notes

Each cycle stores small immutable JSON checkpoints under
`data/company/product_builder/cycles/<cycle_id>/`.
The baseline and candidate C8D reports remain in their original
`browser_checks/` directories. SHA-256 fingerprints detect later edits
to report content and source HTML, but are **not** authenticity guarantees.

One cycle has these maximums: one baseline browser execution, one model call,
one candidate browser execution. Reusing a report counts as the baseline.
Manual approval is required for browser execution, model calls, and C8B apply
independently. Model usage may incur cloud fees. No automatic retries,
self-modifying worker permissions, arbitrary shell, remote deployment, or
application-install privileges.

C8F tests use fake browser results and stubbed model responses; only the
previous C8D runs on the user's actual Windows machine validated live Edge and
Chrome behavior. Test the workflow locally before relying on it for product
decisions.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_product_cycle.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

C8F adds 27 unit tests on top of the 346-test baseline. Expected total:
**373 tests**.
