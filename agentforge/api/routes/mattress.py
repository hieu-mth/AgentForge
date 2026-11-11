"""Owner-authenticated mattress workflow routes (never public ingress)."""
import re

from agentforge.api.routes._shared import UNHANDLED
from agentforge.features.mattress_sales import service

LEAD_ACTION = re.compile(r"/api/mattress/leads/([a-f0-9]{32})/(status|quote|shipping|confirm)\Z")
NOTICE_MARK = re.compile(r"/api/mattress/notices/([a-f0-9]{32})/mark\Z")


def handle(server, path, request, session=None):
    if not path.startswith("/api/mattress/"):
        return UNHANDLED
    if session is None:
        raise PermissionError("Owner session required for mattress mutations")
    db_path = getattr(server, "mattress_db_path", None)
    if path == "/api/mattress/leads":
        if set(request) != {"ack", "lead"} or request["ack"] != "OWNER_RECORD_CONSENTED_LEAD":
            raise PermissionError("Explicit Owner approval and lead payload required")
        return service.create_lead(request["lead"], confirmed=True, db_path=db_path)
    lead_match = LEAD_ACTION.fullmatch(path)
    if lead_match:
        lead_id, action = lead_match.groups()
        if action == "status":
            if set(request) != {"ack", "status"}:
                raise ValueError("Invalid status action")
            return service.change_status(lead_id, request["status"],
                                         ack=request["ack"], db_path=db_path)
        if action == "quote":
            if set(request) != {"ack", "product", "price_vnd"}:
                raise ValueError("Invalid quote payload")
            return service.quote(lead_id, request["product"],
                                 request["price_vnd"], ack=request["ack"],
                                 db_path=db_path)
        if action == "shipping":
            if set(request) != {"ack", "coverage", "fee_vnd", "note"}:
                raise ValueError("Invalid delivery verification payload")
            return service.verify_delivery(
                lead_id, request["coverage"], request["fee_vnd"], request["note"],
                ack=request["ack"], db_path=db_path)
        if set(request) != {"ack", "customer_agreed"}:
            raise ValueError("Invalid confirmation payload")
        return service.confirm_order(
            lead_id, customer_agreed=request["customer_agreed"],
            ack=request["ack"], db_path=db_path)
    notice_match = NOTICE_MARK.fullmatch(path)
    if notice_match:
        if set(request) != {"ack"}:
            raise ValueError("Invalid notice confirmation")
        return service.mark_notified(notice_match.group(1),
                                     ack=request["ack"], db_path=db_path)
    return UNHANDLED
