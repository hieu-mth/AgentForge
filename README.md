# AgentForge

A **local-first, human-controlled AI business research prototype** built with Python, LangGraph and SQLite. Current scope: opportunity research, controlled source review, owner decisions, market intelligence classification, and local customer interview intake/review. **Not** an autonomous operating company, desktop controller, or revenue-generating product.

## Current capabilities

- **Model profiles:** Ollama (`local_primary`) or an opt-in Anthropic-compatible cloud gateway (`cloud_primary`) via environment variables.
- **Research:** two web searches, lead collection, analysis, local reports in `data/research/`.
- **Source review:** explicit public HTTPS host approval, page quote matching, owner review. Matching a quote does **not** verify that the claim is true.
- **Market intelligence:** owner-catalogued vendor claims and advertised prices remain separate from Evaluation evidence.
- **Customer intake (C7A):** anonymized, consent-based interview notes marked `CAPTURED_UNVERIFIED`.
- **Customer review (C7B):** manual retain/follow-up/reject decisions and source fingerprinting. Even retained first-hand accounts are **not** independently verified evidence of demand or payment, and are **not** registered for GO/KILL.

No autonomous customer outreach, publishing, payment, installation, unrestricted code execution, or desktop control is authorized by the research workflow.

## Local setup

Requires Python **3.13+** on Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

The default model uses local Ollama (`qwen3:8b`); make sure Ollama is installed and running with the configured model. To use an approved cloud gateway, fill in your **local ignored** `.env` file with `AGENTFORGE_MODEL_REF=cloud_primary`, `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`. **Never commit tokens or interview data.** Cloud calls can incur charges.

Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Research example (uses configured model and live search):

```powershell
.\.venv\Scripts\python.exe -m agentforge.research "Nhu cầu tự động hóa Excel cho shop online nhỏ tại Việt Nam"
```

Customer interview tools (local, **no network**):

```powershell
.\.venv\Scripts\python.exe -m agentforge.customer_validation questions
.\.venv\Scripts\python.exe -m agentforge.customer_validation summary research-d3188c6a
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review summary research-d3188c6a
```

Interview records require *real* first-hand conversations and consent; don't capture sample JSON. See [C7A](docs/milestones/C7A.md) and [C7B](docs/milestones/C7B.md) for detailed commands, constraints and trust boundaries.

## Data and security

- Generated data is stored in `data/` and ignored by Git. This is **not encryption**; protect the local disk and backups.
- `.env` is ignored by Git, while `.env.example` is safe to share.
- Owner approval is required for source reads and evidence decisions; C7B does not grant spending or execution permissions.
- Path validation and command allowlisting are **not a hardened OS sandbox**. Do not let generated code run with unrestricted system permissions.

## Project status

C7A and C7B are early validation infrastructure. Customer demand, willingness to pay, and paid transactions remain unverified until independently corroborated under a later, explicitly approved workflow.
