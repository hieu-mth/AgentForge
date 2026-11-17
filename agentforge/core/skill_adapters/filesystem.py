"""Approved workspace file creation and byte-for-byte artifact verification."""

POLICY = {
    "filesystem.revise_report": ("product_builder", "owner_gated",
                                 frozenset({"workspace.read", "workspace.write"})),
    "terminal.check": ("product_builder", "owner_gated", frozenset({"process.run"})),
    "filesystem.report": ("product_builder", "owner_gated", frozenset({"workspace.write"})),
}


def dispatch(skill_id, payload):
    from agentforge import gateway
    if skill_id == "filesystem.report":
        return gateway.write_verified_report(payload["path"], payload["content"])
    if skill_id == "filesystem.revise_report":
        return gateway.revise_report(**payload)
    if skill_id == "terminal.check":
        return gateway.run_terminal_recipe(payload["recipe"], payload["directory"])
    raise PermissionError("Unknown workspace skill")
