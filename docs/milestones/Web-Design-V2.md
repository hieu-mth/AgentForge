# Web Design V2 — Luxury websites with local photos

This additive capability upgrades the C8B–C8D static website workflow. As of premium-first Product Builder, the same shared offline design kit also runs during the **first** C8A proposal in one model call; `web_design_v2 prepare` remains an optional revision tool for existing websites. It does **not** turn AgentForge into a fully autonomous web designer or e-commerce platform.

**Implemented**
- An offline CSS design layer (ivory/beige/brown, responsive type, Segoe UI/Tahoma/Arial supporting Vietnamese, keyboard focus, subtle motion and reduced-motion support).
- An **original inline SVG bedroom illustration**, clearly labelled as illustrative, when no genuine photo is supplied.
- Import real owner-supplied PNG/JPG/WebP images into the project's ignored `assets/` folder. No stock-photo download, no remote font or script, no SVG upload.
- Preview copies referenced images; C8D browser validation serves only approved local images and tracks broken images.
- Project-name-based `prepare`, `review`, `test`, `approve` commands. No copy-pasting revision IDs or SHA. The actual write, backup and hash validation remain in C8B.
- Static style-audit markers. **They do not prove visual aesthetics, SEO, sales conversion, or legal product claims.**

## Optional: bring your own genuine mattress photos

```powershell
cd E:\Projects\AgentForge
.\.venv\Scripts\python.exe -m agentforge.web_assets import nem-tu-van "D:\Photos\nem-hero.jpg" hero.jpg --confirm-write
.\.venv\Scripts\python.exe -m agentforge.web_assets list nem-tu-van
```

Each image must be <=6 MiB; maximum 12 images / 30 MiB per product. Flat lowercase filenames only. Import refuses overwrite, scripts, remote assets and unsafe paths. Use only images you have permission to publish.

## Create a new Luxury design proposal and run Edge test

```powershell
.\.venv\Scripts\python.exe -m agentforge.web_design_v2 prepare nem-tu-van --confirm-model-call --confirm-browser-run --browser-channel msedge
```

The command makes **one explicitly approved model call** (possibly billed) and runs Playwright only because you approved it. Generated HTML may execute JS in Edge; HTTP interception is **not** an OS security sandbox. This writes an ignored-data preview and browser report, **not** the actual product website.

## Review without re-running AI

```powershell
$state = .\.venv\Scripts\python.exe -m agentforge.web_design_v2 review nem-tu-van | ConvertFrom-Json
$state
if ($state.status -eq "READY_FOR_OWNER_REVIEW") { Invoke-Item $state.preview_path }
```

You may also prepare without `--confirm-browser-run` and then explicitly test once:

```powershell
.\.venv\Scripts\python.exe -m agentforge.web_design_v2 test nem-tu-van --confirm-browser-run --browser-channel msedge
```

Review the actual HTML source, photos and C8D screenshots. Passing browser checks **does not certify beauty or reliability**.

## Apply only after your final review

```powershell
.\.venv\Scripts\python.exe -m agentforge.web_design_v2 approve nem-tu-van --confirm-reviewed --confirm-write
Invoke-Item ".\workspace\products\nem-tu-van\index.html"
```

Approval requires a passing C8D report, matching photo fingerprints and source SHA, intact C8B revision, and both owner confirmation flags. It uses C8B's backup. No automatic publish/deploy.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_web_design_v2.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

## Premium-first creation (no extra V2 model call)

A new website now starts with the premium design kit in the **first** Product Builder proposal. A real website still requires review and digest-gated owner apply. Generated HTML is untrusted. No second model call or V2 `prepare` step is necessary just to obtain V2 styling.

```powershell
cd D:\AgentForge
$draft = .\.venv\Scripts\python.exe -m agentforge.product_builder propose nem-tu-van "Tạo website tư vấn nệm tiếng Việt sang trọng, có CTA liên hệ và nội dung không bịa đặt." | ConvertFrom-Json
.\.venv\Scripts\python.exe -m agentforge.product_builder inspect $draft.proposal_id
notepad $draft.proposal_path
# Only after owner review:
.\.venv\Scripts\python.exe -m agentforge.product_builder apply $draft.proposal_id --confirm-write --sha256 $draft.sha256
# Optional real browser validation after reviewing HTML/JS:
.\.venv\Scripts\python.exe -m agentforge.browser_validation project nem-tu-van --confirm-browser-run --browser-channel msedge
```

Real local photos can still be imported to an existing product and applied through an approved V2 revision. A generic labeled illustration or model-created inline SVG is used without photos; no real product photograph is fabricated. Browser testing uses optional Playwright, which is not installed by baseline dependencies.
