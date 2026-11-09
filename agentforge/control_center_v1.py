"""Backwards-compatible Owner API imports; canonical implementation is agentforge.api."""
from agentforge.api.auth import COOKIE, SESSION_SECONDS, SENSITIVE_GRANTS, LOCAL_GRANTS
from agentforge.api.static import REACT_DIST, REACT_ASSET_RE, _react_asset
from agentforge.api.routes.bootstrap import _public_task, _owner_attention, _summary
from agentforge.api.routes.mutations import _owner_action
from agentforge.api.server import _Handler, MAX_BODY, create_server, main

if __name__ == "__main__":
    main()
