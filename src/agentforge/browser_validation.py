"""C8D owner-started browser validation for small offline HTML products.

Optional Playwright/Chromium. Rendering executes untrusted page JavaScript:
HTTP routing is not an OS sandbox. No model calls or product modifications.
"""

import argparse
import json
from datetime import datetime, timezone
from uuid import uuid4

from agentforge import product_builder as builder
from agentforge import product_quality as quality
from agentforge import product_revision as revision


DOCUMENT_URL = "http://agentforge.invalid/"
VIEWPORTS = (
    ("mobile", 390, 844),
    ("tablet", 768, 1024),
    ("desktop", 1440, 900),
)
MAX_CAPTURE_HEIGHT = 12000
# "bundled" is Playwright's downloaded Chromium. The other two channels use
# browsers already installed on the host; no installation or download occurs.
BROWSER_CHANNELS = ("bundled", "msedge", "chrome")
EVALUATE_METRICS = """() => {
  const root = document.documentElement;
  const body = document.body;
  return {
    viewport_width: root.clientWidth,
    document_width: Math.max(root.scrollWidth, body ? body.scrollWidth : 0),
    document_height: Math.max(root.scrollHeight, body ? body.scrollHeight : 0),
    title_present: Boolean(document.title.trim())
  };
}"""


def _read_target(kind, identifier):
    if kind == "project":
        slug = builder._check_slug(identifier)
        _, raw, html = revision._source(slug)
        report_id = slug
        source_sha256 = revision._hash(raw)
    elif kind == "revision":
        doc, _, receipt = revision._read_revision(identifier)
        if receipt.exists():
            raise RuntimeError("Revision already applied; check the project instead")
        revision._require_current(doc)
        slug = doc["project_slug"]
        html = doc["files"][0]["content"]
        report_id = identifier
        source_sha256 = revision._hash(html.encode("utf-8"))
    else:
        raise ValueError("Target must be project or revision")
    static = quality.analyze(html)
    if static["status"] == "FAIL":
        raise ValueError("Static checks report FAIL; browser run refused")
    return {
        "target": kind,
        "identifier": report_id,
        "project_slug": slug,
        "html": html,
        "source_sha256": source_sha256,
        "static_status": static["status"],
        "static_warnings": static["warnings"],
    }


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is optional. Install explicitly with: "
            r".\.venv\Scripts\python.exe -m pip install playwright; "
            r".\.venv\Scripts\python.exe -m playwright install chromium"
        ) from exc
    return sync_playwright


def _issue(issues, rule, viewport, message, severity="FAIL"):
    issues.append({
        "rule": rule,
        "severity": severity,
        "viewport": viewport,
        "message": message,
    })


def validate(kind, identifier, *, confirm_browser_run=False, playwright_factory=None, browser_channel="bundled"):
    """Run once only after explicit approval; save screenshots/report to ignored data.

    playwright_factory is injectable for unit tests. It never creates a web server
    or opens a persistent user browser profile.
    """
    if confirm_browser_run is not True:
        raise PermissionError("Explicit --confirm-browser-run is required")
    if browser_channel not in BROWSER_CHANNELS:
        raise ValueError("Unsupported browser channel; use bundled, msedge or chrome")
    target = _read_target(kind, identifier)
    factory = playwright_factory if playwright_factory is not None else _playwright()

    run_id = uuid4().hex
    folder = (
        builder.ROOT / "data" / "company" / "product_builder" / "browser_checks"
        / kind / target["identifier"] / run_id
    )
    report_path = folder / "report.json"
    builder._check_path_chain(report_path)
    for label, _, _ in VIEWPORTS:
        builder._check_path_chain(folder / (label + ".png"))

    findings = []
    screens = []
    html = target["html"]
    source_bytes = html.encode("utf-8")
    with factory() as playwright:
        launch_args = {"headless": True}
        if browser_channel != "bundled":
            launch_args["channel"] = browser_channel
        # Chrome/Edge channels use an installed browser, not an automatic
        # download. Keep the bundled default for users who installed Chromium.
        browser = playwright.chromium.launch(**launch_args)
        try:
            # Each viewport uses a separate incognito context. No cookies,
            # service workers, downloads or persistent browser profile.
            for label, width, height in VIEWPORTS:
                blocked = []
                errors = []
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    service_workers="block",
                    accept_downloads=False,
                    permissions=[],
                )
                try:
                    # Fulfill the only approved HTML route from memory. Abort
                    # all other ordinary HTTP requests. This does NOT isolate
                    # browser WebSockets/other processes or replace an OS sandbox.
                    def route_request(route):
                        request = route.request
                        if request.url == DOCUMENT_URL and request.method == "GET":
                            route.fulfill(status=200,
                                          content_type="text/html; charset=utf-8",
                                          body=source_bytes)
                        else:
                            blocked.append(request.resource_type)
                            route.abort("blockedbyclient")

                    context.route("**/*", route_request)
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)[:180]))
                    page.goto(DOCUMENT_URL, wait_until="load", timeout=10000)
                    page.wait_for_timeout(200)
                    metrics = page.evaluate(EVALUATE_METRICS)
                    if (not isinstance(metrics, dict)
                            or any(type(metrics.get(key)) is not int for key in (
                                "viewport_width", "document_width", "document_height"))):
                        raise RuntimeError("Invalid browser measurements")
                    if metrics["document_width"] > metrics["viewport_width"] + 2:
                        _issue(findings, "horizontal_overflow", label,
                               f"Document width {metrics['document_width']}px exceeds "
                               f"viewport {metrics['viewport_width']}px")
                    if errors:
                        _issue(findings, "javascript_errors", label,
                               f"{len(errors)} uncaught JavaScript error(s)")
                    if blocked:
                        _issue(findings, "blocked_requests", label,
                               f"{len(blocked)} off-document request(s) blocked")
                    screenshot = None
                    if metrics["document_height"] > MAX_CAPTURE_HEIGHT:
                        _issue(findings, "capture_height", label,
                               "Page too tall for bounded screenshot",
                               severity="WARN")
                    else:
                        folder.mkdir(parents=True, exist_ok=False) if not folder.exists() else None
                        path = folder / (label + ".png")
                        builder._check_path_chain(path)
                        page.screenshot(path=str(path), full_page=True,
                                        animations="disabled", timeout=10000)
                        screenshot = str(path)
                    screens.append({
                        "viewport": label, "width": width, "height": height,
                        "document_width": metrics["document_width"],
                        "document_height": metrics["document_height"],
                        "javascript_error_count": len(errors),
                        "blocked_request_count": len(blocked),
                        "screenshot_path": screenshot,
                    })
                finally:
                    context.close()
        finally:
            browser.close()

    if kind == "revision":
        doc, _, receipt = revision._read_revision(identifier)
        if receipt.exists():
            _issue(findings, "revision_applied_during_check", "all",
                   "Revision was applied during browser validation")
        else:
            try:
                revision._require_current(doc)
            except (RuntimeError, OSError, ValueError):
                _issue(findings, "revision_stale_during_check", "all",
                       "Original index.html changed during validation")
    else:
        current = revision._source(target["project_slug"])[1]
        if revision._hash(current) != target["source_sha256"]:
            _issue(findings, "source_changed_during_check", "all",
                   "Project index.html changed during validation")

    failures = sum(x["severity"] == "FAIL" for x in findings)
    warnings = sum(x["severity"] == "WARN" for x in findings)
    status = "FAIL" if failures else "WARN" if warnings or target["static_warnings"] else "PASS"
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": kind,
        "identifier": identifier,
        "project_slug": target["project_slug"],
        "source_sha256": target["source_sha256"],
        "browser_channel": browser_channel,
        "status": status,
        "failures": failures,
        "warnings": warnings + target["static_warnings"],
        "findings": findings,
        "static_status": target["static_status"],
        "viewports": screens,
        "browser_rendered": True,
        "javascript_executed": True,
        "browser_run_approved": True,
        "network_note": "HTTP requests intercepted, NOT a hardened network/OS sandbox",
        "security_verified": False,
        "spending_authorized": False,
        "deployment_authorized": False,
        "product_modified": False,
    }
    folder.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    return {
        "status": status,
        "run_id": run_id,
        "browser_channel": browser_channel,
        "report_path": str(report_path),
        "screenshots": [x["screenshot_path"] for x in screens if x["screenshot_path"]],
        "failures": failures,
        "warnings": report["warnings"],
        "product_modified": False,
        "deployment_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="C8D opt-in local Chromium validation; executes untrusted HTML JavaScript")
    sub = parser.add_subparsers(dest="target", required=True)
    for kind in ("project", "revision"):
        cmd = sub.add_parser(kind)
        cmd.add_argument("identifier", help="Project slug or pending revision ID")
        cmd.add_argument("--confirm-browser-run", action="store_true")
        cmd.add_argument(
            "--browser-channel", choices=BROWSER_CHANNELS, default="bundled",
            help="bundled Chromium (needs download), or locally installed msedge/chrome",
        )
    args = parser.parse_args()
    result = validate(args.target, args.identifier,
                      confirm_browser_run=args.confirm_browser_run,
                      browser_channel=args.browser_channel)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "FAIL":
        parser.exit(2)


if __name__ == "__main__":
    main()
