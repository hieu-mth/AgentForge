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
