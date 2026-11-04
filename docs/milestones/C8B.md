# C8B — Owner-gated revisions of an existing static web product

This is a small, offline-file revision workflow. It does **not** run the page,
open a browser, install packages, test in a browser, contact customers or deploy.
Only `index.html` can be revised in C8B. C8A creation remains unchanged.

## Workflow

```powershell
cd E:\Projects\AgentForge

# An existing C8A product is required. This uses the configured model and
# may send the current HTML source to a paid cloud gateway if selected in .env.
.\.venv\Scripts\python.exe -m agentforge.product_revision propose shop-landing "Cải thiện bố cục và CTA cho mobile, giữ chức năng offline."

# Replace REVISION_ID with the ID printed by propose.
.\.venv\Scripts\python.exe -m agentforge.product_revision inspect REVISION_ID
.\.venv\Scripts\python.exe -m agentforge.product_revision diff REVISION_ID
notepad .\data\company\product_builder\revisions\REVISION_ID.json

# ONLY after reviewing the proposed code and agreeing to replace index.html:
.\.venv\Scripts\python.exe -m agentforge.product_revision apply REVISION_ID --confirm-write --sha256 SHA256_FROM_INSPECT
```

The `propose`, `inspect`, and `diff` commands never modify product files.
`apply` requires explicit approval and the SHA-256 digest of the **whole proposal**.
It rechecks that the original `index.html` bytes match the source fingerprint.
Stale proposals are refused; generate a new proposal against the current file.
It creates a verified backup before replacing the file and stores a receipt:

- Original: `workspace/products/<slug>/index.html`
- Proposal: `data/company/product_builder/revisions/<id>.json`
- Backup: `data/company/product_builder/backups/<slug>/<id>/index.html`
- Receipt: `data/company/product_builder/applied/<id>.json`

All three data paths are Git-ignored and are **not encrypted**. A failed apply
may leave a backup or lock requiring manual investigation; do not automatically
remove backup/receipt files. Other project files remain unchanged.

## Limits and safety

- Not a security sandbox: text filters only reject obvious unsafe content; review
  the full generated HTML/JS before opening it in a browser.
- Revisions are not autonomous: `apply` never calls a model, shell or network.
- `propose` does call your configured model once, and if `cloud_primary` is
  selected, the **existing page source** is shared with that gateway; do not
  propose on pages containing secrets or sensitive customer data.
- No permission to spend, execute, publish, or deploy is granted.
- Backups are local files, not a replacement for disk backups. SHA hashes detect
  accidental changes, not a hostile actor with filesystem write permission.
- Do not edit or delete the source while `apply` is running; local locking is
  advisory and not a hardened OS security boundary.

Tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_product_revision.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected count after 228 tests from C8A: **256**. Confirm on Windows/CI.

## Gateway text-response diagnostics (2026-11-04)

For cloud-only **product_builder** text generation, the Anthropic-compatible
adapter now allows up to 8,192 output tokens rather than 2,048. This is a
ceiling, not a guaranteed response length; models that use internal reasoning
may consume part of it. It may increase cost when cloud output is long.
Research text requests stay at 2,048; structured JSON requests stay at 4,096.

If the provider replies with only non-text content, AgentForge reports the
provider's stop_reason, block type names, output-token usage (when available),
and token ceiling, **not** the API token, prompt, or generated content.
A response marked `stop_reason=max_tokens` is rejected even if it includes
partial HTML. Failed generations do not create revision proposals. There is
**no automatic retry** and no write to the product.

This improves diagnosis and gives full HTML more room, but cannot establish
that a specific third-party gateway will return complete text. Check the error
and provider behavior before another paid call.
