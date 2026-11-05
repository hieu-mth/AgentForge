"""Compatibility alias for the canonical agentforge.core.brain_store module.

Aliases rather than duplicated imports preserve existing monkeypatching,
module-level DB constants, and all legacy CLI entrypoints.
"""
if __name__ == "__main__":
    from agentforge.core.brain_store import main
    main()
else:
    import sys
    from agentforge.core import brain_store as _implementation
    sys.modules[__name__] = _implementation
