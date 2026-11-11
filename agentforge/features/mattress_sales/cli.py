"""Owner CLI for referral-first mattress MVP.

Manual intake or bounded CSV exports from a separately trusted public form.
Optional Telegram bot delivery has explicit consent and durable claim before
the request; an ambiguous delivery is NEVER automatically resent.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from agentforge.features.mattress_sales import service, site

BOT_TOKEN = re.compile(r"[0-9]{6,12}:[A-Za-z0-9_-]{25,90}\Z")
CHAT_ID = re.compile(r"-?[0-9]{5,20}\Z")
CSV_COLUMNS = ("external_id", "customer_name", "phone", "interest",
               "area", "consent_to_contact")
MAX_CSV_BYTES = 256 * 1024
MAX_CSV_ROWS = 500


def _telegram(message):
    """One bounded request, no urllib proxy/redirect and no token in logs."""
    token = os.environ.get("AGENTFORGE_MATTRESS_TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("AGENTFORGE_MATTRESS_TELEGRAM_CHAT_ID", "")
    if not BOT_TOKEN.fullmatch(token) or not CHAT_ID.fullmatch(chat):
        raise ValueError("Telegram credentials are not configured")
    body = json.dumps({"chat_id": chat, "text": message,
                       "disable_web_page_preview": True},
                      ensure_ascii=False).encode("utf-8")
    if len(body) > 3500:
        raise ValueError("Notification text is too large")
    conn = http.client.HTTPSConnection("api.telegram.org", timeout=10)
    try:
        conn.request("POST", "/bot" + token + "/sendMessage", body=body,
                     headers={"Content-Type": "application/json",
                              "Accept": "application/json"})
        response = conn.getresponse()
        raw = response.read(4097)
        if response.status != 200 or len(raw) > 4096:
            raise RuntimeError("Telegram response is not verified")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("Telegram did not acknowledge delivery")
        return True
    finally:
        conn.close()


def dispatch_telegram(notice_id, *, confirmed=False, db_path=None, sender=None):
    if confirmed is not True:
        raise PermissionError("Explicit approval required before contacting Telegram")
    # No claiming / side effects when configuration is absent.
    if sender is None:
        if (not BOT_TOKEN.fullmatch(os.environ.get(
                "AGENTFORGE_MATTRESS_TELEGRAM_BOT_TOKEN", "")) or
                not CHAT_ID.fullmatch(os.environ.get(
                    "AGENTFORGE_MATTRESS_TELEGRAM_CHAT_ID", ""))):
            raise ValueError("Telegram credentials are not configured")
        sender = _telegram
    message = service.message_for_notice(notice_id, db_path=db_path)
    service.claim_notice(notice_id, ack="OWNER_AUTHORIZE_EXTERNAL_MESSAGE",
                         db_path=db_path)
    try:
        acknowledged = sender(message) is True
    except Exception:
        # The provider may have delivered the message before the socket died:
        # NEVER automatically retry. Owner can inspect Telegram then mark.
        acknowledged = False
    return service.finish_notice(
        notice_id, confirmed_delivered=acknowledged, db_path=db_path)


def _import_payloads(path):
    source = Path(path)
    service._path(source)  # guard junctions/symlinks; no output to the source
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_CSV_BYTES:
        raise service.MattressError("Approved CSV must be a bounded local file")
    with source.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or tuple(reader.fieldnames) != CSV_COLUMNS:
            raise service.MattressError("CSV columns must match the documented contract")
        result = []
        for row in reader:
            if len(result) >= MAX_CSV_ROWS or None in row:
                raise service.MattressError("CSV row count or columns invalid")
            reference = row["external_id"]
            if not isinstance(reference, str) or not service.REF.fullmatch(reference):
                raise service.MattressError("Untrusted external lead identifier")
            if row["consent_to_contact"] != "YES":
                raise PermissionError("CSV row lacks explicit contact consent")
            request_id = hashlib.sha256(
                ("agentforge:mattress:web-import:" + reference).encode()).hexdigest()[:32]
            payload, _ = service._lead_payload({
                "request_id": request_id,
                "source": "WEBSITE_IMPORT", "source_ref": reference,
                "customer_name": row["customer_name"], "phone": row["phone"],
                "interest": row["interest"], "area": row["area"],
                "consent_to_contact": True,
            })
            result.append(payload)
    # Reject repeated references before any DB changes.
    refs = [item["source_ref"] for item in result]
    if len(refs) != len(set(refs)):
        raise service.MattressError("CSV contains repeated external IDs")
    return result


def import_csv(path, *, confirmed=False, consent_provenance=False, db_path=None):
    if confirmed is not True or consent_provenance is not True:
        raise PermissionError("Owner must verify source and customer opt-in")
    rows = _import_payloads(path)
    results = {"created": 0, "duplicates": 0, "partial": False}
    # Each row is independently committed; rerun is idempotent. A late DB
    # write failure can leave a partial batch (never claim all-or-nothing).
    for payload in rows:
        try:
            report = service.create_lead(payload, confirmed=True,
                                         db_path=db_path)
        except Exception:
            results["partial"] = results["created"] > 0
            raise
        if report["created"]:
            results["created"] += 1
        else:
            results["duplicates"] += 1
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="AgentForge mattress referral MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("lead-add", help="Record a consented referral or walk-in")
    create.add_argument("--name", required=True)
    create.add_argument("--phone", required=True)
    create.add_argument("--interest", default="")
    create.add_argument("--area", default="")
    create.add_argument("--source", choices=("REFERRAL", "WALK_IN"), default="REFERRAL")
    create.add_argument("--confirm-consent", action="store_true")

    listing = sub.add_parser("summary", help="Counts only; never prints contact data")

    importer = sub.add_parser("import-csv", help="Import approved CSV from a hosted form")
    importer.add_argument("--file", required=True)
    importer.add_argument("--confirm-import", action="store_true")
    importer.add_argument("--confirm-consent-provenance", action="store_true")

    export = sub.add_parser("site-export", help="Write a static local contact website")
    export.add_argument("--settings", required=True)
    export.add_argument("--confirm-export", action="store_true")
    export.add_argument("--replace-sha")

    notify = sub.add_parser("notify-telegram", help="Send exactly one approved notice")
    notify.add_argument("--notice-id", required=True)
    notify.add_argument("--confirm-external-send", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "summary":
            result = service.summary()
        elif args.command == "lead-add":
            result = service.create_lead({
                "request_id": uuid4().hex, "source": args.source,
                "source_ref": None, "customer_name": args.name,
                "phone": args.phone, "interest": args.interest,
                "area": args.area, "consent_to_contact": args.confirm_consent,
            }, confirmed=args.confirm_consent)
            result = {"created": result["created"],
                      "lead_id": result["lead"]["lead_id"], "customer_data_printed": False}
        elif args.command == "import-csv":
            result = import_csv(args.file, confirmed=args.confirm_import,
                                consent_provenance=args.confirm_consent_provenance)
        elif args.command == "site-export":
            location = Path(args.settings)
            service._path(location)
            if not location.is_file() or location.stat().st_size > 25_000:
                raise ValueError("Approved site settings file missing/too large")
            settings = json.loads(location.read_text(encoding="utf-8"))
            result = site.export(settings, confirmed=args.confirm_export,
                                 replace_sha=args.replace_sha)
        else:
            result = dispatch_telegram(args.notice_id,
                                       confirmed=args.confirm_external_send)
    except (ValueError, KeyError, PermissionError, OSError):
        parser.exit(2, "Operation blocked. Check local Owner state; no automatic retry.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
