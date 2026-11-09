"""Compatibility alias for the canonical agentforge.core.skill_registry module.

Aliases rather than duplicated imports preserve existing monkeypatching,
module-level DB constants, and all legacy CLI entrypoints.
"""
if __name__ == "__main__":
    from agentforge.core.skill_registry import main
    main()
else:
    import sys
    from agentforge.core import skill_registry as _implementation
    sys.modules[__name__] = _implementation
