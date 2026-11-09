"""Static allowlist of domain skill adapters; no manifest-provided Python imports.

Adding a skill requires a reviewed code policy and explicit handler in one domain
adapter, plus its validated TOML manifest. Dispatch never trusts a path from TOML.
"""
from . import analytics, growth, media, research, web

_ADAPTERS = (web, research, media, analytics, growth)
POLICY = {}
_HANDLERS = {}
for _module in _ADAPTERS:
    for _skill_id, _rule in _module.POLICY.items():
        if _skill_id in POLICY:
            raise RuntimeError(f"Duplicate trusted skill adapter: {_skill_id}")
        POLICY[_skill_id] = _rule
        _HANDLERS[_skill_id] = _module.dispatch


def dispatch(skill_id, payload):
    """Run only a statically registered handler; caller must check permissions."""
    try:
        handler = _HANDLERS[skill_id]
    except KeyError as exc:
        raise PermissionError("No trusted adapter") from exc
    return handler(skill_id, payload)
