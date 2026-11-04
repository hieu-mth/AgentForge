# C8D — Owner-started Chromium browser validation

C8D checks real rendering of C8A/C8B **single-file static HTML**. It is
local-first: screenshots and JSON reports stay in Git-ignored `data/`.
It does not call AI, change product files, auto-fix, deploy, or contact customers.

## One-time optional installation (Windows PowerShell)

The baseline `pip install -e .` does **not** install Playwright or browsers.
Only if you choose to use browser validation, explicitly install:

```powershell
cd E:\Projects\AgentForge
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
```

Both commands download software and require your approval. You can run baseline
unit tests **without** Playwright and Chromium. Do not run as Administrator.

## Check the currently applied product

```powershell
.\.venv\Scripts\python.exe -m agentforge.browser_validation project shop-landing --confirm-browser-run
```

Or check a **pending**, not-yet-applied C8B proposal:

```powershell
.\.venv\Scripts\python.exe -m agentforge.browser_validation revision YOUR_REVISION_ID --confirm-browser-run
```

For a revision already applied, check the project instead. The tool also
rejects stale and tampered proposals or content with static C8C `FAIL`.

The tool creates one new report folder per run:

```text
data/company/product_builder/browser_checks/
  project/shop-landing/<run_id>/
    mobile.png
    tablet.png
    desktop.png
    report.json
```

For revisions, the folder begins with `revision/<revision_id>/`. Nothing in
`workspace/products/` is edited. The report records the source SHA-256 so
a later comparison can tell which file version was examined.

## What it actually validates

The headless Chromium browser renders each size in a **separate ephemeral
browser context**:

- Mobile: **390 × 844**
- Tablet: **768 × 1024**
- Desktop: **1440 × 900**

It captures a screenshot (up to 12,000 px page height), detects document-wide
horizontal overflow, uncaught JavaScript errors and non-document network
requests. It returns `PASS`, `WARN` or `FAIL`. A FAIL exits the CLI
with code 2, and still writes a report to a unique folder.

**Not covered:** visual aesthetics, visual regression, real device emulation
beyond fixed viewport sizes, clicking every interactive element, WCAG audit,
or proof that the application is secure. Owner should review screenshots.

## Browser security boundary (important)

`--confirm-browser-run` explicitly allows Chromium to execute **untrusted
JavaScript in the HTML**; it is not permission to deploy, spend, or modify
the product. It uses a temporary non-persistent browser context with service
workers blocked, no downloads, and only one in-memory HTML document served
at `http://agentforge.invalid/`. Other ordinary HTTP requests are intercepted
and aborted. No HTTP server is started.

**This is not a hardened OS/network sandbox.** Page scripts or browser
implementation details may use network APIs outside ordinary HTTP routing
(e.g. WebSockets/WebRTC), and a browser exploit could escape the context.
Do not run unknown or sensitive content on a privileged machine. Inspect
the HTML/JS before browser validation and use a separate low-privilege OS
user or VM for untrusted material. No browser session is launched on import
or when the explicit confirmation flag is absent.

If your current product includes relative CSS/JS/image assets in addition to
the single HTML file, C8D does **not** load them. Use a self-contained
`index.html` for accurate results; off-document loads are reported as blocked.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_browser_validation.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

C8D adds **17 isolated unit tests** using a fake Playwright adapter; the regular
GitHub Actions suite does not run a real Chromium browser. You must complete
the owner-started Chromium check locally to validate actual rendering.
