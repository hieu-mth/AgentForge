"""Trusted, allowlisted research skill policies and lazy adapters.

No handler is imported at discovery time. The runner checks grants before dispatch.
"""
from contextlib import redirect_stdout
from io import StringIO

POLICY = {
    "research.opportunity": ("opportunity_researcher", "owner_gated",
                             frozenset({"model.invoke", "network.search", "workspace.write"})),
    "research.source_review": ("source_reviewer", "owner_gated",
                               frozenset({"workspace.read", "workspace.write",
                                          "model.invoke", "network.read"})),
}


def dispatch(skill_id, payload):
    if skill_id == "research.opportunity":
        from agentforge.research import run
        with redirect_stdout(StringIO()):
            return run(payload["topic"])
    if skill_id == "research.source_review":
        from agentforge.source_review import run_review
        with redirect_stdout(StringIO()):
            return run_review(payload["task_id"], payload["allowed_hosts"],
                              max_pages=payload.get("max_pages", 4),
                              approve_read_only=True)
    raise PermissionError("No trusted adapter")
