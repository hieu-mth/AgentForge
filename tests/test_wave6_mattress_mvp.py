"""Wave 6 mattress referral MVP: actual local DB, Owner API and offline artifacts.

Only synthetic numbers/people, temporary SQLite and local HTTP fixtures.
No Telegram delivery, public deployment, real PII or logistics calls.
"""
import csv
import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from agentforge.api.server import create_server
from agentforge.features.mattress_sales import cli, service, site


def payload(request_id=None, source="REFERRAL", source_ref=None):
    return {
        "request_id": request_id or uuid4().hex,
        "source": source, "source_ref": source_ref,
        "customer_name": "Khách hàng thử nghiệm",
        "phone": "0900000000", "interest": "Nệm theo kích thước",
        "area": "Cần hỏi bên vận chuyển", "consent_to_contact": True,
    }


class MattressStoreTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.db = self.root / "data" / "company" / "mattress_sales.sqlite3"

    def new(self, **extra):
        p = payload()
        p.update(extra)
        return service.create_lead(p, confirmed=True, db_path=self.db)["lead"]

    def _notices(self):
        return service.list_notices(db_path=self.db)

    def test_reads_do_not_initialize_schema_or_directory(self):
        self.assertEqual(service.list_leads(db_path=self.db), [])
        self.assertEqual(service.list_notices(db_path=self.db), [])
        self.assertEqual(service.summary(db_path=self.db)["total"], 0)
        self.assertEqual(service.report(db_path=self.db)["public_ingress"],
                         "NOT_CONNECTED")
        self.assertFalse(self.db.exists())
        self.assertFalse(self.db.parent.exists())
        with self.assertRaises(KeyError):
            service.get_lead(uuid4().hex, db_path=self.db)

    def test_explicit_consent_and_input_guards(self):
        p = payload()
        with self.assertRaises(PermissionError):
            service.create_lead(p, db_path=self.db)
        with self.assertRaises(PermissionError):
            service.create_lead({**p, "consent_to_contact": False},
                                confirmed=True, db_path=self.db)
        for phone in ["<script>", "090000000", "0900\n000000", "+1-2345", ""]:
            with self.subTest(phone=phone), self.assertRaises(service.MattressError):
                service.create_lead({**p, "phone": phone},
                                    confirmed=True, db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_durable_idempotence_and_no_duplicate_notification(self):
        request = payload()
        first = service.create_lead(request, confirmed=True, db_path=self.db)
        again = service.create_lead(request, confirmed=True, db_path=self.db)
        self.assertTrue(first["created"])
        self.assertFalse(again["created"])
        self.assertEqual(first["lead"]["lead_id"], again["lead"]["lead_id"])
        self.assertEqual(len(self._notices()), 1)
        with self.assertRaises(service.MattressError):
            service.create_lead({**request, "phone": "0911111111"},
                                confirmed=True, db_path=self.db)
        imported = payload(source="WEBSITE_IMPORT", source_ref="hosted:form-0001")
        self.assertTrue(service.create_lead(
            imported, confirmed=True, db_path=self.db)["created"])
        imported_retry = {**imported, "request_id": uuid4().hex}
        self.assertFalse(service.create_lead(
            imported_retry, confirmed=True, db_path=self.db)["created"])
        self.assertEqual(service.summary(db_path=self.db)["total"], 2)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)

    def test_order_requires_human_quote_verified_carrier_and_customer_agreement(self):
        lead = self.new()
        ident = lead["lead_id"]
        with self.assertRaises(PermissionError):
            service.change_status(ident, "CONTACTED", ack="yes", db_path=self.db)
        service.change_status(ident, "CONTACTED",
                              ack="OWNER_CONTACTED_CUSTOMER", db_path=self.db)
        with self.assertRaises(PermissionError):
            service.quote(ident, "Nệm mẫu", 4000000, ack="AI_CONFIRMED",
                          db_path=self.db)
        with self.assertRaises(service.MattressError):
            service.confirm_order(ident, customer_agreed=True,
                                  ack="OWNER_CONFIRM_ORDER", db_path=self.db)
        service.quote(ident, "Nệm mẫu đã kiểm tra", 4000000,
                      ack="OWNER_SET_QUOTE", db_path=self.db)
        with self.assertRaises(service.MattressError):
            service.confirm_order(ident, customer_agreed=True,
                                  ack="OWNER_CONFIRM_ORDER", db_path=self.db)
        service.verify_delivery(ident, "UNSUPPORTED", None,
                                "Đơn vị giao chưa hỗ trợ", ack="OWNER_CHECKED_CARRIER",
                                db_path=self.db)
        with self.assertRaises(service.MattressError):
            service.confirm_order(ident, customer_agreed=True,
                                  ack="OWNER_CONFIRM_ORDER", db_path=self.db)
        service.verify_delivery(ident, "SUPPORTED", 150000,
                                "Đã hỏi đơn vị vận chuyển", ack="OWNER_CHECKED_CARRIER",
                                db_path=self.db)
        with self.assertRaises(PermissionError):
            service.confirm_order(ident, customer_agreed=False,
                                  ack="OWNER_CONFIRM_ORDER", db_path=self.db)
        with self.assertRaises(PermissionError):
            service.confirm_order(ident, customer_agreed=True,
                                  ack="wrong", db_path=self.db)
        confirmed = service.confirm_order(ident, customer_agreed=True,
                                          ack="OWNER_CONFIRM_ORDER", db_path=self.db)
        self.assertEqual(confirmed["status"], "OWNER_CONFIRMED")
        self.assertEqual(confirmed["shipping_fee_vnd"], 150000)
        self.assertEqual(service.summary(db_path=self.db)["confirmed_orders"], 1)
        self.assertEqual([x["kind"] for x in self._notices()].count("ORDER_CONFIRMED"), 1)
        with self.assertRaises(service.MattressError):
            service.confirm_order(ident, customer_agreed=True,
                                  ack="OWNER_CONFIRM_ORDER", db_path=self.db)
        service.change_status(ident, "DELIVERY_PLANNED",
                              ack="OWNER_PLANNED_DELIVERY", db_path=self.db)
        delivered = service.change_status(ident, "DELIVERED",
                                          ack="OWNER_CONFIRMED_DELIVERY", db_path=self.db)
        self.assertEqual(delivered["status"], "DELIVERED")
        with self.assertRaises(service.MattressError):
            service.change_status(ident, "DELIVERED",
                                  ack="OWNER_CONFIRMED_DELIVERY", db_path=self.db)

    def test_no_fake_shipping_vnd_or_leap_to_confirmed_state(self):
        lead = self.new()
        ident = lead["lead_id"]
        with self.assertRaises(service.MattressError):
            service.change_status(ident, "DELIVERED",
                                  ack="OWNER_CONFIRMED_DELIVERY", db_path=self.db)
        service.change_status(ident, "CONTACTED",
                              ack="OWNER_CONTACTED_CUSTOMER", db_path=self.db)
        service.quote(ident, "Nệm mẫu", 1000, ack="OWNER_SET_QUOTE", db_path=self.db)
        for amount in (-1, 1.5, True, "150000"):
            with self.subTest(amount=amount), self.assertRaises(service.MattressError):
                service.verify_delivery(ident, "SUPPORTED", amount, "Đã kiểm tra",
                                        ack="OWNER_CHECKED_CARRIER", db_path=self.db)
        self.assertEqual(service.get_lead(ident, db_path=self.db)["shipping_coverage"],
                         "UNKNOWN")

    def test_notification_requires_real_manual_send_ack(self):
        lead = self.new()
        notice = self._notices()[0]
        text = service.message_for_notice(notice["notice_id"], db_path=self.db)
        self.assertIn("0900000000", text)
        self.assertIn("Chưa có đơn", text)
        self.assertEqual(self._notices()[0]["status"], "PENDING")
        with self.assertRaises(PermissionError):
            service.mark_notified(notice["notice_id"], ack="COPY_ONLY", db_path=self.db)
        self.assertEqual(self._notices()[0]["status"], "PENDING")
        result = service.mark_notified(
            notice["notice_id"], ack="OWNER_ATTEST_ACTUALLY_NOTIFIED",
            db_path=self.db)
        self.assertEqual(result["status"], "SENT_MANUAL")
        with self.assertRaises(service.MattressError):
            service.mark_notified(notice["notice_id"],
                                  ack="OWNER_ATTEST_ACTUALLY_NOTIFIED", db_path=self.db)

    def test_telegram_dispatch_opt_in_and_ambiguous_timeout_cannot_retry(self):
        self.new()
        notice = self._notices()[0]["notice_id"]
        calls = []
        def sender(value):
            calls.append(value)
            raise TimeoutError("May already have delivered")
        with self.assertRaises(PermissionError):
            cli.dispatch_telegram(notice, sender=sender, db_path=self.db)
        self.assertEqual(calls, [])
        result = cli.dispatch_telegram(notice, confirmed=True,
                                       sender=sender, db_path=self.db)
        self.assertEqual(result["status"], "NEEDS_REVIEW")
        self.assertEqual(len(calls), 1)
        self.assertEqual(self._notices()[0]["status"], "NEEDS_REVIEW")
        with self.assertRaises(service.MattressError):
            cli.dispatch_telegram(notice, confirmed=True,
                                  sender=lambda _: True, db_path=self.db)
        self.assertEqual(len(calls), 1)
        service.mark_notified(notice, ack="OWNER_ATTEST_ACTUALLY_NOTIFIED",
                              db_path=self.db)

    def test_crash_stuck_dispatching_requires_owner_delivery_review(self):
        self.new()
        notice = self._notices()[0]["notice_id"]
        service.claim_notice(notice, ack="OWNER_AUTHORIZE_EXTERNAL_MESSAGE",
                             db_path=self.db)
        self.assertEqual(self._notices()[0]["status"], "DISPATCHING")
        with self.assertRaises(service.MattressError):
            cli.dispatch_telegram(notice, confirmed=True, sender=lambda _: True,
                                  db_path=self.db)
        self.assertEqual(self._notices()[0]["status"], "DISPATCHING")
        settled = service.mark_notified(
            notice, ack="OWNER_ATTEST_ACTUALLY_NOTIFIED", db_path=self.db)
        self.assertEqual(settled["status"], "SENT_MANUAL")

    def test_confirmed_telegram_ack_has_one_durable_notice(self):
        self.new()
        notice = self._notices()[0]["notice_id"]
        with patch.dict("os.environ", {
                "AGENTFORGE_MATTRESS_TELEGRAM_BOT_TOKEN": "",
                "AGENTFORGE_MATTRESS_TELEGRAM_CHAT_ID": ""}):
            with self.assertRaises(ValueError):
                cli.dispatch_telegram(notice, confirmed=True, db_path=self.db)
        self.assertEqual(self._notices()[0]["status"], "PENDING")
        out = cli.dispatch_telegram(notice, confirmed=True, sender=lambda _: True,
                                    db_path=self.db)
        self.assertEqual(out["status"], "SENT")
        with self.assertRaises(service.MattressError):
            cli.dispatch_telegram(notice, confirmed=True, sender=lambda _: True,
                                  db_path=self.db)

    def test_prevalidated_csv_import_and_idempotent_replay(self):
        csvpath = self.root / "hosted-form.csv"
        rows = [
            ["external_id","customer_name","phone","interest","area","consent_to_contact"],
            ["hosted-001","Khách thử một","0900000000","Nệm foam","Khu vực chưa rõ","YES"],
            ["hosted-002","Khách thử hai","0911111111","Nệm lò xo","","YES"],
        ]
        with csvpath.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        with self.assertRaises(PermissionError):
            cli.import_csv(csvpath, confirmed=True, db_path=self.db)
        self.assertFalse(self.db.exists())
        result = cli.import_csv(csvpath, confirmed=True,
                                consent_provenance=True, db_path=self.db)
        self.assertEqual(result, {"created": 2, "duplicates": 0, "partial": False})
        replay = cli.import_csv(csvpath, confirmed=True,
                                consent_provenance=True, db_path=self.db)
        self.assertEqual(replay["created"], 0)
        self.assertEqual(replay["duplicates"], 2)
        self.assertEqual(service.summary(db_path=self.db)["total"], 2)
        self.assertEqual(len(self._notices()), 2)

    def test_invalid_csv_is_rejected_before_mutation(self):
        csvpath = self.root / "bad.csv"
        csvpath.write_text(
            "external_id,customer_name,phone,interest,area,consent_to_contact\n"
            "hosted-001,Khách A,0900000000,Nệm mẫu,,YES\n"
            "hosted-002,Khách B,0911111111,Nệm mẫu,,NO\n", encoding="utf-8")
        with self.assertRaises(PermissionError):
            cli.import_csv(csvpath, confirmed=True,
                           consent_provenance=True, db_path=self.db)
        self.assertFalse(self.db.exists())


class MattressStaticSiteTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.settings = {
            "brand": "Tư vấn nệm gia đình", "phone": "0900000000",
            "zalo_phone": "0900000000",
            "intro": "Tư vấn theo nhu cầu, có người hỗ trợ.",
            "products": [{"name": "Nệm mẫu <script>alert(1)</script>",
                          "description": "Chỉ là mẫu thử, giá và giao hàng chưa xác minh."}],
        }

    def test_static_escape_and_no_hidden_checkout_or_lead_exfiltration(self):
        result = site.render(self.settings)
        self.assertIn("lang=\"vi\"", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertNotIn("<script", result.lower())
        self.assertNotIn("<form", result.lower())
        self.assertNotIn("fetch(", result)
        self.assertNotIn("checkout", result.lower())
        self.assertIn("tel:0900000000", result)
        self.assertIn("https://zalo.me/0900000000", result)
        self.assertIn("Không tự cam kết giá", result)
        self.assertLess(len(result.encode("utf-8")), site.MAX_SITE_BYTES)

    def test_site_requires_owner_contact_and_exact_replacement_sha(self):
        with self.assertRaises(service.MattressError):
            site.render({**self.settings, "phone": ""})
        with self.assertRaises(PermissionError):
            site.export(self.settings, output_dir=self.root / "site")
        result = site.export(self.settings, confirmed=True,
                             output_dir=self.root / "site")
        self.assertEqual(result["status"], "LOCAL_SITE_EXPORTED_NOT_PUBLISHED")
        self.assertFalse(result["public_url_verified"])
        self.assertFalse(result["public_form_connected"])
        path = self.root / "site" / "index.html"
        initial = path.read_bytes()
        with self.assertRaises(service.MattressError):
            site.export(self.settings, confirmed=True,
                        output_dir=self.root / "site")
        with self.assertRaises(service.MattressError):
            site.export(self.settings, confirmed=True,
                        output_dir=self.root / "site",
                        replace_sha="f" * 64)
        self.assertEqual(path.read_bytes(), initial)
        updated = site.export({**self.settings, "intro": "Tư vấn mới với đầy đủ kiểm tra"},
                              confirmed=True, output_dir=self.root / "site",
                              replace_sha=hashlib.sha256(initial).hexdigest())
        self.assertNotEqual(updated["sha256"], result["sha256"])

    def test_empty_inventory_avoids_inventing_stock_price_and_shipping(self):
        output = site.render({**self.settings, "products": [], "zalo_phone": None})
        self.assertIn("Đang cập nhật sản phẩm", output)
        self.assertNotIn("zalo.me", output)
        self.assertNotIn("₫", output)


class MattressOwnerHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "mattress.sqlite3"
        self.server = create_server(
            0, owner_code="synthetic-owner-code-wave6",
            mattress_db_path=self.db)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._shutdown)
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.cookie = None
        self.csrf = None

    def _shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=4)

    def req(self, method, path, body=None, *, cookie=True, csrf=True, origin=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=8)
        headers = {"Host": self.host}
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        if method == "POST":
            headers["Content-Type"] = "application/json"
            headers["Origin"] = "http://" + self.host if origin is None else origin
            if csrf and self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        connection.request(method, path, body=(json.dumps(body).encode() if
                           method == "POST" else None), headers=headers)
        result = connection.getresponse()
        raw = result.read()
        status, meta = result.status, dict(result.getheaders())
        connection.close()
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw.decode()
        return status, value, meta

    def login(self):
        status, value, headers = self.req(
            "POST", "/api/login", {"code": "synthetic-owner-code-wave6"})
        self.assertEqual(status, 200, value)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, value, _ = self.req("GET", "/api/session")
        self.assertEqual(status, 200)
        self.csrf = value["csrf"]

    def test_owner_auth_csrf_and_local_only_reads(self):
        self.assertEqual(self.req("GET", "/api/mattress")[0], 401)
        self.assertFalse(self.db.exists())
        self.login()
        s, value, _ = self.req("GET", "/api/mattress")
        self.assertEqual(s, 200)
        self.assertEqual(value["summary"]["total"], 0)
        self.assertFalse(self.db.exists())
        data = {"ack": "OWNER_RECORD_CONSENTED_LEAD", "lead": payload()}
        self.assertEqual(self.req("POST", "/api/mattress/leads", data, csrf=False)[0], 403)
        self.assertEqual(self.req("POST", "/api/mattress/leads", data,
                                  origin="https://other.example")[0], 403)
        self.assertFalse(self.db.exists())
        s, result, _ = self.req("POST", "/api/mattress/leads", data)
        self.assertEqual(s, 200, result)
        self.assertTrue(result["created"])
        lead_id = result["lead"]["lead_id"]
        s, report, _ = self.req("GET", "/api/mattress")
        self.assertEqual(s, 200)
        self.assertEqual(report["leads"][0]["lead_id"], lead_id)
        self.assertNotIn("payload_sha", json.dumps(report))
        notice_id = report["notices"][0]["notice_id"]
        s, text, _ = self.req("GET",
                              f"/api/mattress/notices/{notice_id}/message")
        self.assertEqual(s, 200)
        self.assertIn("0900000000", text["message"])
        self.assertEqual(self.req(
            "POST", f"/api/mattress/notices/{notice_id}/mark",
            {"ack": "NOT_SENT"})[0], 400)
        self.assertEqual(self.req(
            "POST", f"/api/mattress/notices/{notice_id}/mark",
            {"ack": "OWNER_ATTEST_ACTUALLY_NOTIFIED"})[0], 200)
        self.assertEqual(self.req("GET", "/api/mattress", cookie=False)[0], 401)

    def test_public_contact_submission_is_not_an_unprotected_endpoint(self):
        code, _, _ = self.req("POST", "/api/mattress/leads", {
            "ack": "OWNER_RECORD_CONSENTED_LEAD", "lead": payload()})
        self.assertEqual(code, 401)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
