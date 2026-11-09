"""WebApp/Website revisions, source review and apply actions."""
from agentforge.api.routes._shared import UNHANDLED


def handle(server, path, request, session=None):
    if path.startswith("/api/webapps/") and (
            path.endswith("/revision") or path.endswith("/apply") or path.endswith("/rollback")):
        from agentforge import webapp_developer
        parts = path.split("/")
        if len(parts) != 5 or parts[1:3] != ["api", "webapps"]:
            raise ValueError("Invalid application action")
        proposal_id, action = parts[3], parts[4]
        expected = ({"ack", "sha256", "feedback"} if action == "revision" else
                    {"ack", "sha256", "target_proposal_id", "target_sha256"}
                    if action == "rollback" else {"ack", "sha256"})
        if set(request) != expected:
            raise ValueError("Invalid application request fields")
        provider = webapp_developer.provider(proposal_id)
        proposal = provider.inspect(proposal_id)
        if request.get("sha256") != proposal["sha256"]:
            raise PermissionError("Application proposal SHA mismatch")
        if (session is None or session.get("reviewed_webapps", {}).get(proposal_id)
                != proposal["sha256"]):
            raise PermissionError("Inspect this exact app proposal before authorizing")
        if action == "revision":
            if request["ack"] != "REQUEST_REVISION":
                raise PermissionError("Explicit app revision acknowledgment required")
            from agentforge.webapp_feedback import request_revision
            return request_revision(
                proposal_id, proposal["sha256"], request["feedback"],
                brain_db_path=server.brain_db_path,
                analytics_db_path=server.analytics_db_path,
                growth_db_path=server.growth_db_path)
        if action == "rollback":
            if provider is webapp_developer.base:
                raise PermissionError("Rollback of template marketplace is unsupported")
            if request["ack"] != "RESTORE_REACT_VERSION":
                raise PermissionError("Explicit source rollback acknowledgment required")
            target_id, target_sha = request["target_proposal_id"], request["target_sha256"]
            # Both versions must have been explicitly inspected with their exact
            # source SHA in this Owner session; no guessed/forged ancestry.
            if (session.get("reviewed_webapps", {}).get(target_id) != target_sha):
                raise PermissionError("Inspect target ancestor SHA before restoring")
            return provider.rollback(proposal_id, proposal["sha256"],
                                     target_id, target_sha, confirm_restore=True)
        if request["ack"] != "APPLY_WEBAPP":
            raise PermissionError("Explicit app source approval required")
        return provider.apply(
            proposal_id, sha256=proposal["sha256"], confirm_write=True)
    if path.startswith("/api/proposals/") and path.endswith("/revision"):
        from agentforge.website_feedback import request_revision
        parts = path.split("/")
        if len(parts) != 5 or set(request) != {"ack", "sha256", "feedback"}:
            raise ValueError("Invalid revision request")
        if request["ack"] != "REQUEST_REVISION":
            raise PermissionError("Owner must explicitly request a revision")
        ident = parts[3]
        if (session is None or session.get("reviewed_proposals", {}).get(ident)
                != request["sha256"]):
            raise PermissionError("Review this exact proposal SHA before requesting changes")
        return request_revision(
            ident, request["sha256"], request["feedback"],
            brain_db_path=server.brain_db_path,
            analytics_db_path=server.analytics_db_path,
            growth_db_path=server.growth_db_path)
    if path.startswith("/api/proposals/") and path.endswith("/apply"):
        from agentforge import product_builder
        parts = path.split("/")
        if len(parts) != 5:
            raise ValueError("Invalid proposal action")
        proposal_id = parts[3]
        metadata = product_builder.inspect(proposal_id)
        if (request.get("ack") != "APPLY_PROPOSAL"
                or request.get("sha256") != metadata["sha256"]):
            raise PermissionError("Explicit matching proposal SHA required")
        if (session is None or session.get("reviewed_proposals", {}).get(
                proposal_id) != metadata["sha256"]):
            raise PermissionError("Inspect original proposal in this session before applying")
        return product_builder.apply(
            proposal_id, confirm_write=True, sha256=metadata["sha256"])
    return UNHANDLED
