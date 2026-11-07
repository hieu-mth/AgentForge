# V4.0b — AI marketplace source proposals (owner-gated)

## What is implemented

A new allowlisted Goal template (webapp.draft) delegates to webapp.create
through the existing S4/S1 permission gates. The natural prompt intake now
routes "Shopee", "marketplace", "giỏ hàng" and other ecommerce requests to
this separate skill, rather than pretending V3.6 static landing pages can
implement real shopping-cart interactions.

The model selects an original marketplace brand, intro content, color,
3–6 categories and 6–12 fictional products via a strict JSON schema.
The trusted compiler assembles the already reviewed V4.0a React/Vite
marketplace app. It contains **working client-side** search, category filters,
sorting, product details and a demo cart. It never installs dependencies,
executes scripts, calls payment APIs, deploys or logs into accounts.

Output: SHA-bound, immutable local proposal under
data/company/webapp_builder/proposals. The separate apply step copies
approved source into workspace/webapps/<slug>. Never overwrite existing
projects. No automatic retries or extra AI calls.

## Exact workflow (PowerShell)

1. Update the repo and Dashboard, start Control Center as before.
2. In Giao việc submit a marketplace request. Review Goal plan, SHA and model
   invocation permissions; run once.
3. Open the successful Task result. Read project ID, proposal ID and SHA.
4. From the repository root, inspect:
   .\.venv\Scripts\python.exe -m agentforge.webapp_builder inspect <proposal_id>
5. Open the path to that local JSON proposal in an editor, review all files,
   then (only after owner acceptance):
   .\.venv\Scripts\python.exe -m agentforge.webapp_builder apply <proposal_id> --sha256 <sha> --confirm-write
6. Optionally run the approved project after installing dependencies manually:
   cd workspace\webapps\<project_slug>
   npm.cmd install
   npm.cmd test
   npm.cmd run build
   npm.cmd run dev
7. Open http://127.0.0.1:5184 and test search, cart, mobile UI manually.

## Scope, limitations and safeguards

V4.0b is intentionally **not arbitrary AI-generated React code**. The AI may
choose DATA and branding; the known React behavior is trusted source from the
reference application. A general AI Developer that writes arbitrary files
requires a separate sandboxed build runner first. No CI passing claim implies
that Ollama on the Owner Windows machine was tested with the model for this
specific prompt; that remains a real-hardware acceptance check.

V3.6 landing-page skill web.create remains unmodified. Backend remains Python,
SQLite, no multi-service rewrite. Existing proposal/session grants do not
silently extend to this new skill. Source is review-only until the Owner
performs explicit manual apply and optional manual npm commands.
