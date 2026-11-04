# AgentForge

**Local-first, human-controlled AI business research and product prototyping.** AgentForge is a Python 3.13 prototype built with LangGraph and SQLite. It can research opportunities, manage owner-reviewed market/customer evidence, and propose small static web products. It is **not** an autonomous company, hardened sandbox, or production deployment system.

## Capabilities

- **Model routing:** local Ollama (`local_primary`, `qwen3:8b`) or an opt-in Anthropic-compatible gateway (`cloud_primary`).
- **Opportunity research:** two focused searches, source leads, cautious reports and local checkpoints; search snippets are **not** verified facts.
- **Source/evidence review:** approved HTTPS page reads, quote matching, owner decisions, and separate vendor market-intelligence classifications.
- **Customer validation (C7A–C7C):** anonymous, consent-based interview intake; retain/follow-up/reject decisions; two owner-confirmed accounts can support only the `customer_problem` scope. Neither interviews nor advertised prices prove payments or demand on their own.
- **AI Product Builder V1 (C8A):** generates one offline, self-contained `index.html` as a **proposal**. Only an owner-approved, digest-matched `apply` creates files in `workspace/products/<slug>/`. No automatic execution, browser automation or deployment.
- **Product revisions (C8B):** proposes changes to an existing `index.html`, shows a read-only diff, checks the original file fingerprint, and requires explicit digest-matched approval before replacing it. The prior version is backed up locally.

All generated text/code is untrusted. No workflow grants autonomous customer outreach, spending, publishing, package installation, or arbitrary shell execution.

## Local setup — Windows PowerShell

Requires **Python 3.13+**.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

Default model: local Ollama (`qwen3:8b`), which must be installed and running. For an approved cloud gateway, set `AGENTFORGE_MODEL_REF=cloud_primary`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_AUTH_TOKEN` in the **gitignored** `.env`. Cloud requests may incur charges; never commit credentials.

Run the tests (no live model credentials or customer interviews required):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The repository's [GitHub Actions CI](.github/workflows/ci.yml) runs the same suite on Windows and Python 3.13 for pushes/PRs targeting `main`.

## Usage

### Research

```powershell
.\.venv\Scripts\python.exe -m agentforge.research "Nhu cầu tự động hóa Excel cho shop online nhỏ tại Việt Nam"
```

Research outputs stay under `data/research/`.

### Product Builder V1 — owner-gated

```powershell
# Propose only. May call a paid cloud model if cloud_primary is configured.
.\.venv\Scripts\python.exe -m agentforge.product_builder propose shop-landing "Tạo landing page tiếng Việt, responsive, giới thiệu dịch vụ tự động hóa Excel và bảng giá minh họa."

# Copy the ID printed by propose, then inspect the proposal metadata and JSON.
$proposalId = "PASTE_PROPOSAL_ID"
.\.venv\Scripts\python.exe -m agentforge.product_builder inspect $proposalId
notepad ".\data\company\product_builder\proposals\$proposalId.json"

# Only after inspecting and approving the generated source:
$sha256 = "PASTE_SHA256_FROM_INSPECT"
.\.venv\Scripts\python.exe -m agentforge.product_builder apply $proposalId --confirm-write --sha256 $sha256
```

Applying writes `workspace/products/shop-landing/index.html` but does **not** open, execute or deploy it. Review HTML/JS before opening it in a browser. The C8A creation flow never overwrites an existing project.

### Product revisions (C8B) — owner-gated

Use this only after a product already exists in `workspace/products/`. `propose` sends the current HTML to the configured model (and possibly a paid cloud gateway); it never edits the product. Review the proposed content and diff before approving the write.

```powershell
.\.venv\Scripts\python.exe -m agentforge.product_revision propose shop-landing "Cải thiện giao diện trên mobile, tăng khoảng trắng và làm rõ nút CTA."
$revisionId = "PASTE_REVISION_ID"
.\.venv\Scripts\python.exe -m agentforge.product_revision inspect $revisionId
.\.venv\Scripts\python.exe -m agentforge.product_revision diff $revisionId
notepad ".\data\company\product_builder\revisions\$revisionId.json"

# Only after reviewing the changes:
$revisionSha = "PASTE_SHA256_FROM_INSPECT"
.\.venv\Scripts\python.exe -m agentforge.product_revision apply $revisionId --confirm-write --sha256 $revisionSha
```

C8B backs up the prior `index.html` under `data/company/product_builder/backups/`, refuses stale proposals, and never launches a browser or deploys code. See [C8B](docs/milestones/C8B.md).

### Customer interviews

```powershell
.\.venv\Scripts\python.exe -m agentforge.customer_validation questions
.\.venv\Scripts\python.exe -m agentforge.customer_validation summary research-d3188c6a
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review summary research-d3188c6a
```

Only capture real, consented, anonymous interviews. Do **not** capture example or generated interview content as real evidence. See [C7A](docs/milestones/C7A.md), [C7B](docs/milestones/C7B.md), [C7C](docs/milestones/C7C.md), [C8A](docs/milestones/C8A.md), and [C8B](docs/milestones/C8B.md).

## Local data, security and status

- `data/`, `workspace/`, and `.env` are ignored by Git, **not encrypted**. Protect local disks and backups.
- SHA-256 checks detect later modifications; they are not evidence that an interview truly occurred or that generated code is safe.
- URL allowlists and path checks are **not** an OS sandbox. Run with minimum OS permissions and review source before execution.
- No real customer demand, willingness to pay, sales or revenue has been independently verified.
- Current milestone: **Builder revisions (C8B)**. Next: local preview and safe, explicitly approved checks. No autonomous browser control or deployment.
