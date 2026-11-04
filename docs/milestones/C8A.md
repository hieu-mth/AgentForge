# C8A — AI Product Builder V1 (static web only)

**Status:** owner-gated code generation MVP. This is not an autonomous developer or
an isolated OS sandbox. Generated code is **untrusted** until inspected by the owner.

## Scope and trust boundary

- AgentForge's `product_builder` worker (configured to use `local_primary` with
  machine-specific `AGENTFORGE_MODEL_REF` override) **proposes** up to four simple
  static web text files: `index.html`, `styles.css`, `app.js`, `README.md`.
- Proposals saved under `data/company/product_builder/proposals/`, which Git ignores.
  `propose` may call the configured model provider (cloud usage may incur charges)
  but does **not** write into `workspace/products/`.
- `inspect` reveals proposal ID, project, filenames, sizes and content digest.
  Open the JSON proposal manually to inspect all source before applying.
- `apply` requires **both** `--confirm-write` and an exact SHA256 digest shown
  by `inspect`; it creates only new files in `workspace/products/<slug>/`.
  It rejects pre-existing product directories and unsafe filenames. Never
  automatically executes code, shell commands, npm, Python, browser, apps or deploy.
- Obvious remote resources/network APIs are rejected, but text checks are **not**
  a security audit. Inspect generated HTML/JS before manually opening the site.
  File path checks are not a hardened filesystem sandbox; don't run as admin.
- No money, publishing, customer outreach or account access authorized.

## Windows PowerShell

From `E:\Projects\AgentForge` after C8A is installed:

```powershell
# Caution: may call a paid cloud gateway if AGENTFORGE_MODEL_REF=cloud_primary.
.\.venv\Scripts\python.exe -m agentforge.product_builder propose shop-landing "Tạo landing page tĩnh tiếng Việt cho dịch vụ tự động hóa Excel, có mô tả, lợi ích và nút liên hệ dạng placeholder; không gọi mạng ngoài."

# Copy the proposal_id returned by the previous command:
.\.venv\Scripts\python.exe -m agentforge.product_builder inspect <proposal_id>

# Review the generated proposal file before any product files are written:
notepad .\data\company\product_builder\proposals\<proposal_id>.json

# Only if you approve the exact proposal and digest:
.\.venv\Scripts\python.exe -m agentforge.product_builder apply <proposal_id> --confirm-write --sha256 <64_character_sha256_from_inspect>

# Open or edit the files after independently reviewing their contents.
# NO automatic browser opening or code execution is implemented.
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_product_builder.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

C8A adds 22 unit tests to the 198-test C7C baseline (expected **220** total
if the C7C full suite passed). No live gateway or real product execution is
part of the unit test suite.

## Hotfix: robust real-model output (2026-11-04)

The default `propose` runtime now generates one complete self-contained
`index.html` as plain text. Long source code no longer needs to be escaped
as JSON by the model. It still validates the file, saves a reviewable proposal
only, and requires the same `inspect -> apply --confirm-write --sha256` gate.
Incomplete HTML is rejected without creating a proposal. The injected
`model_client` test hook continues to accept the C8A structured JSON schema.
No model retry is performed automatically, avoiding unexpected extra cloud calls.
