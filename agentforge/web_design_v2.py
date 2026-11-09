"""Web Design V2: premium, local-first revisions with a single project handle.

One explicitly authorized model call creates an ordinary C8B revision. Local
image assets and a deterministic design kit improve reliable rendering. C8C
checks & previews; C8D optionally runs Edge/Chrome. Owner alone may approve.
No external images, paid asset providers, publishing, or automatic apply.
"""
import argparse
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from agentforge import browser_validation as browser
from agentforge import product_builder as builder
from agentforge import product_cycle
from agentforge import product_quality as quality
from agentforge import product_revision as revision
from agentforge import web_assets


# Share the exact design kit with first-time website creation.
from agentforge.web_design_kit import BEDROOM_ART, DESIGN_CSS, upgrade_html as _html_upgrade

BRIEF = (
    "Thiết kế lại website hiện có theo Luxury Premium: ivory/beige/nâu trầm, "
    "chuyên nghiệp, thoáng, sang trọng, mobile-first. Font hệ thống hỗ trợ "
    "dấu tiếng Việt; hero ấn tượng, card đồng bộ, CTA tư vấn nổi bật, "
    "FAQ/quy trình rõ ràng, tương tác hover tinh tế. Giữ tên, số liên hệ "
    "và các thông tin thật/placeholder hiện tại. Không bịa thương hiệu, "
    "giá, bảo hành, chứng nhận hay đánh giá. Không dùng CDN, ảnh từ mạng "
    "hay analytics. Dùng ảnh local đã liệt kê nếu có."
)



def _latest_path(slug):
    slug = builder._check_slug(slug)
    path = (builder.ROOT / "data" / "company" / "product_builder"
            / "web_design_v2" / slug / "latest.json")
    builder._check_path_chain(path)
    return path


def _save_latest(slug, data):
    path = _latest_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    builder._check_path_chain(path)
    temp = path.with_name(uuid4().hex + ".tmp")
    builder._check_path_chain(temp)
    try:
        with temp.open("x", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _load_latest(slug):
    path = _latest_path(slug)
    if not path.is_file() or path.stat().st_size > 8_000:
        raise FileNotFoundError("No V2 revision for this project. Run prepare first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict)
            or set(data) != {"revision_id", "sha256", "assets", "browser"}
            or not isinstance(data["revision_id"], str)
            or not builder.PROPOSAL_RE.fullmatch(data["revision_id"])
            or not isinstance(data["sha256"], str)
            or not builder.SHA_RE.fullmatch(data["sha256"])
            or not isinstance(data["assets"], list)
            or not isinstance(data["browser"], (dict, type(None)))):
        raise ValueError("Invalid V2 checkpoint")
    doc, _, receipt = revision._read_revision(data["revision_id"])
    if doc["project_slug"] != slug or data["sha256"] != doc["sha256"]:
        raise RuntimeError("V2 checkpoint and C8B proposal mismatch")
    if receipt.exists():
        return data, doc, True
    revision._require_current(doc)
    current = web_assets.verify_references(slug, doc["files"][0]["content"])
    if current != data["assets"]:
        raise RuntimeError("LOCAL_IMAGES_CHANGED: photo differs from reviewed V2 proposal")
    return data, doc, False


def _browser_snapshot(slug, revision_id, browser_result):
    snap = product_cycle._snapshot_candidate(slug, revision_id, browser_result["run_id"])
    return snap


def _check_browser(slug, doc, saved_browser):
    if saved_browser is None:
        return None
    if not isinstance(saved_browser, dict) or set(saved_browser) != {
            "run_id", "report_sha256", "status"}:
        raise ValueError("Invalid saved browser result")
    fresh = _browser_snapshot(slug, doc["revision_id"], saved_browser)
    if fresh != saved_browser:
        raise RuntimeError("Browser report changed since V2 validation")
    return fresh


def _style_audit(html):
    # Structure and offline assets only: this is NOT an aesthetic AI review.
    return {"utf8_meta": bool(re.search(r'(?i)<meta\s+charset\s*=\s*["\x27]?utf-8', html)),
            "vietnamese_lang": bool(re.search(r'(?i)<html\b[^>]*\blang\s*=\s*["\x27]vi', html)),
            "system_font_stack": "Segoe UI" in html and "Tahoma" in html,
            "has_visual": bool(re.search(r'(?i)<img\b|<svg\b', html)),
            "reduced_motion": "prefers-reduced-motion" in html,
            "aesthetic_quality_verified": False}


def prepare(slug, *, confirm_model_call=False, confirm_browser_run=False,
            browser_channel="bundled", model_client=None, browser_runner=None):
    """One model proposal plus optional one browser run, no product HTML write."""
    slug = builder._check_slug(slug)
    if confirm_model_call is not True:
        raise PermissionError("Explicit --confirm-model-call is required")
    if confirm_browser_run and browser_channel not in browser.BROWSER_CHANNELS:
        raise ValueError("Invalid browser channel")
    assets = web_assets.list_images(slug)
    names = ", ".join("assets/" + a["name"] for a in assets[:8])
    request = BRIEF + (" Ảnh được phép: " + names + "." if names else
                       " Chưa có ảnh thật: dùng minh họa offline.")
    request = request[:590]

    def upgrade(prompt, *, worker_id):
        if model_client is None:
            from agentforge.model import generate
            raw = generate(
                "WEB DESIGN V2 REQUIREMENTS: refined luxury composition, "
                "complete HTML under 10500 UTF-8 bytes before post-processing. "
                "Keep all text truthful; use CSS only inline. "
                "Use <img src='assets/filename'> for allowed provided photos; "
                "otherwise prepare a visual illustration. Return raw HTML only.\n"
                + prompt, worker_id=worker_id)
        else:
            raw = model_client(prompt, worker_id=worker_id)
        return _html_upgrade(raw, assets)

    revised = revision.propose(slug, request, model_client=upgrade)
    quality_result = quality.check_revision(revised["revision_id"])
    if quality_result["status"] == "FAIL":
        raise ValueError("V2 static checks FAIL; revision remains unapplied")
    preview = quality.preview_revision(revised["revision_id"])
    doc, _, _ = revision._read_revision(revised["revision_id"])
    linked = web_assets.verify_references(slug, doc["files"][0]["content"])
    record = {"revision_id": revised["revision_id"], "sha256": revised["sha256"],
              "assets": linked, "browser": None}
    _save_latest(slug, record)

    if confirm_browser_run:
        runner = browser_runner if browser_runner is not None else browser.validate
        outcome = runner("revision", revised["revision_id"],
                         confirm_browser_run=True, browser_channel=browser_channel)
        record["browser"] = _browser_snapshot(slug, revised["revision_id"], outcome)
        _save_latest(slug, record)

    return review(slug, preview_path=preview["preview_path"])


def test(slug, *, confirm_browser_run=False, browser_channel="bundled", browser_runner=None):
    if confirm_browser_run is not True:
        raise PermissionError("Explicit --confirm-browser-run required")
    if browser_channel not in browser.BROWSER_CHANNELS:
        raise ValueError("Invalid browser channel")
    data, doc, applied = _load_latest(slug)
    if applied:
        raise RuntimeError("Revision already applied")
    if data["browser"] is not None:
        raise RuntimeError("Browser already tested for this V2 proposal; no implicit retry")
    runner = browser_runner if browser_runner is not None else browser.validate
    result = runner("revision", data["revision_id"],
                    confirm_browser_run=True, browser_channel=browser_channel)
    data["browser"] = _browser_snapshot(slug, data["revision_id"], result)
    _save_latest(slug, data)
    return review(slug)


def review(slug, *, preview_path=None):
    slug = builder._check_slug(slug)
    data, doc, applied = _load_latest(slug)
    # C8F's candidate validator intentionally rejects already-applied C8B
    # proposals; preserve the final state without revalidating that candidate.
    browser_state = None if applied else _check_browser(slug, doc, data["browser"])
    if applied:
        status = "APPLIED_VIA_C8B"
    elif browser_state is None:
        status = "AWAITING_BROWSER_TEST"
    elif browser_state["status"] == "PASS":
        status = "READY_FOR_OWNER_REVIEW"
    else:
        status = "BROWSER_ISSUES_REVIEW_REQUIRED"
    path = (builder.ROOT / "data" / "company" / "product_builder"
            / "previews" / doc["revision_id"] / "index.html")
    builder._check_path_chain(path)
    if not applied and (not path.is_file()
                        or path.read_bytes() != doc["files"][0]["content"].encode("utf-8")):
        raise RuntimeError("Preview missing or modified; rerun preview-revision")
    if not applied:
        for asset in data["assets"]:
            preview_asset = path.parent / "assets" / asset["name"]
            builder._check_path_chain(preview_asset)
            if (not preview_asset.is_file()
                    or revision._hash(preview_asset.read_bytes()) != asset["sha256"]):
                raise RuntimeError("Preview image missing or changed")
    return {"status": status, "project_slug": slug,
            "revision_id": doc["revision_id"],
            "preview_path": str(path if preview_path is None else preview_path),
            "browser_run_id": browser_state["run_id"] if browser_state else None,
            "browser_status": browser_state["status"] if browser_state else None,
            "assets": [x["name"] for x in data["assets"]],
            "style_audit": _style_audit(doc["files"][0]["content"]),
            "product_modified": applied,
            "automatic_approval": False,
            "deployment_authorized": False}


def approve(slug, *, confirm_reviewed=False, confirm_write=False):
    """One terminal command, owner only; delegates C8B's exact digest gate."""
    if confirm_reviewed is not True or confirm_write is not True:
        raise PermissionError("Explicit --confirm-reviewed and --confirm-write required")
    slug = builder._check_slug(slug)
    data, doc, applied = _load_latest(slug)
    if applied:
        raise RuntimeError("Revision already applied")
    checked = _check_browser(slug, doc, data["browser"])
    if checked is None or checked["status"] != "PASS":
        raise PermissionError("Passing C8D browser report required before V2 approval")
    quality_result = quality.check_revision(data["revision_id"])
    if quality_result["status"] == "FAIL":
        raise PermissionError("Static quality gate failed")
    result = revision.apply(data["revision_id"], confirm_write=True, sha256=data["sha256"])
    return {"status": result["status"], "project_slug": slug,
            "revision_id": data["revision_id"],
            "backup_path": result["backup_path"],
            "product_path": str(builder.PRODUCTS / slug / "index.html"),
            "automatic_approval": False, "deployment_authorized": False}


def main():
    parser = argparse.ArgumentParser(
        description="Web Design V2: luxury layout, local photos, Vietnamese typography")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="One model call; prepare preview and optional browser screenshots")
    p.add_argument("slug")
    p.add_argument("--confirm-model-call", action="store_true")
    p.add_argument("--confirm-browser-run", action="store_true")
    p.add_argument("--browser-channel", choices=browser.BROWSER_CHANNELS, default="bundled")
    p = sub.add_parser("review", help="Show latest preview/status for a project")
    p.add_argument("slug")
    p = sub.add_parser("test", help="Run one browser test on the V2 revision")
    p.add_argument("slug")
    p.add_argument("--confirm-browser-run", action="store_true")
    p.add_argument("--browser-channel", choices=browser.BROWSER_CHANNELS, default="bundled")
    p = sub.add_parser("approve", help="Owner-reviewed apply of latest revision through C8B")
    p.add_argument("slug")
    p.add_argument("--confirm-reviewed", action="store_true")
    p.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.slug,
                         confirm_model_call=args.confirm_model_call,
                         confirm_browser_run=args.confirm_browser_run,
                         browser_channel=args.browser_channel)
    elif args.command == "review":
        result = review(args.slug)
    elif args.command == "test":
        result = test(args.slug, confirm_browser_run=args.confirm_browser_run,
                      browser_channel=args.browser_channel)
    else:
        result = approve(args.slug, confirm_reviewed=args.confirm_reviewed,
                         confirm_write=args.confirm_write)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
