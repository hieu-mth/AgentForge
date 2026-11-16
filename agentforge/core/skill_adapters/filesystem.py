"""Approved workspace file creation and byte-for-byte artifact verification."""

POLICY = {
    "filesystem.report": ("product_builder", "owner_gated", frozenset({"workspace.write"})),
}


def dispatch(skill_id, payload):
    if skill_id != "filesystem.report":
        raise PermissionError("Unknown filesystem skill")
    from agentforge.gateway import write_verified_report
    return write_verified_report(payload["path"], payload["content"])
