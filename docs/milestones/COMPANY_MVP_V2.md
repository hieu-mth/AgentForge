# AgentForge V2.0 — Local-First Company MVP Pilot

**Release scope:** a usable owner-supervised local business workflow, **not** an autonomous legal company, not an online SaaS, and not independently verified sales.

V2 integrates existing S1 skills, S2 offline media production (V1.5), S3 analytics, S4 planning/Goal reviews, S5 growth/lead bookkeeping, V1.3 bounded model delegation and V1.4 business Quality Gate with one authenticated Control Center.

## Version mapping and acceptance

| Milestone | Implemented workflow | Owner gate |
|---|---|---|
| V1.6 | Dashboard: read and change bounded Autopilot daily call policy; inspect full SHA-verified storyboard text and decide APPROVE/REJECT from the browser | Authenticated localhost session, CSRF, explicit action, content digest match, inspection recorded per session; no automatic model call |
| V1.7 | S4 Goal Planner / templates and existing read-only scheduling; new V2 deterministic next-owner-action scorecard | Goal plan SHA + explicit owner approval and existing skill grants. No unrestricted agent-to-agent authority |
| V1.8 | Existing local-only website proposal/review/apply flow and consent-attested, **anonymous** S5 leads. V2 campaign KPI view | Source SHA review before applying website. No public deployment, contact collector or customer PII store |
| V1.9 | V1.5 MP4 generation/approval, existing S5 manual YouTube/TikTok ZIP handoff, post attestation and owner-recorded cash/commission | Explicit rights, video SHA checks, channel package/handoff; owner performs platform publication |
| V2.0 | Company scorecard via the authenticated dashboard and python -m agentforge.company_v2 report, launch blockers and next owner actions | Reports provenance, absence of independent verification and unmet launch gates rather than false success |

Important: V1.7–V1.9 compose and surface **existing verified S4/S5 features**; V2 does **not** add automatic social login, network deployment, customer contact ingestion, payment execution, AI model web browsing, or actual lead attribution.

## On Windows (PowerShell 5.1)

First inspect local changes before pulling:

    cd D:\AgentForge
    git status --short
    git switch main
    git pull --ff-only origin main
    .\.venv\Scripts\python.exe -m unittest tests.test_company_v2 -v

Restart the old Control Center so it loads new Python and JS:

    .\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780

In **Tổng quan**:

- **V2 Autopilot Owner Control** lets the owner explicitly set enabled and daily_cap (0–10) without queuing or dispatching model calls. Existing used_today does not reset, and the daily call estimate is not provider-billing enforcement.
- **AI Draft Review Queue** allows inspecting the stored original storyboard in a read-only escaped JSON modal. The server validates the entire output SHA against V1.4 review metadata. APPROVE is restricted to PASS_HEURISTIC and requires the same session to inspect the draft first. Neither approval nor rejection publishes or applies content.
- **Storyboard Editor (local)** creates owned PNG/SRT/WAV assets. The existing V1.5 media_workflow_v15 render CLI requires explicit FFmpeg subprocess consent. Open and watch the resulting MP4 before video approval. The video approval remains CLI-only until secure video streaming exists.
- **V2.0 Business Operations Pilot** shows existing anonymous lead counts, campaign counts, owner-recorded posts, approved local video count and missing conditions; do not mistake these for verified sales.
- **Goals & Phê duyệt**, **Websites**, **Growth & Revenue**, **Schedules** continue to use the existing owner-approved workflows.

Read-only CLI audit:

    .\.venv\Scripts\python.exe -m agentforge.company_v2 report
    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 report
    .\.venv\Scripts\python.exe -m agentforge.quality_v14 inbox
    .\.venv\Scripts\python.exe -m agentforge.media_workflow_v15 report

Manual owner-led lead and commission pilot:

1. Create a real campaign (synthetic:false, budget_vnd:0) in **Growth & Revenue**. This does **not** spend money or set up an ad account.
2. Generate the local website proposal under **Websites**, inspect the source and apply by SHA. It remains in workspace/products until the owner separately arranges deployment. Do not place fabricated business address, phone number, price or warranty on the site.
3. For a visitor who explicitly consented to contact, the owner records an anonymous lead_new event (website or other source), then updates the anonymous lead status in the existing S5 flow. No name/email/phone is accepted. The owner must handle customer contact using an approved external channel, not this SQLite schema.
4. Generate + review video locally; manually prepare and upload the S5 ZIP via an account owned by the user, then record public post permalink with post_attest. No auto-publish or platform verification.
5. If commission is actually paid, record the amount via the existing owner-attested ledger. owner_confirmed is still **not bank-verified** and **not independently audited**.

## Explicit V2 exit criteria / blockers

A green Windows CI confirms code quality of the local prototype, not real-world usability. Actual business V2 field validation additionally requires: owner to test a genuine generated website on a phone, owner to watch the real MP4 on Windows, consent-attested real lead contact flow, human upload, actual platform receipt, verified commission evidence where relevant and an operator checking privacy disclosures. None of these can be performed on a remote GitHub repository without the user's own services and real-world evidence. The V2 report therefore sets real_business_validated:false and bank_verified_profit_vnd:null until independently measured.

Security: localhost-only owner auth, CSRF checks, no permission expansion in a browser payload, no arbitrary skill dispatch, no customer PII database, no external account OAuth, no automatic publishing or financial execution, no unrestricted background agent jobs. Data at rest in SQLite is **not encrypted**; back up securely.

## Technical regression

CI on Windows 3.13, Node frontend and PowerShell 5.1 acceptance. For local evidence, run:

    .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    .\.venv\Scripts\python.exe -m agentforge.company_v2 report

Record actual user screenshots and the output of the report for launch review. The V2 report is a deterministic suggestion engine, not an LLM-powered autonomous CEO.
