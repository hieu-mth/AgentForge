"""Compatibility alias for the canonical agentforge.core.brain_runner module.

Aliases rather than duplicated imports preserve existing monkeypatching,
module-level DB constants, and all legacy CLI entrypoints.
"""
if __name__ == "__main__":
    from agentforge.core.brain_runner import main
    main()
else:
    import sys
    from agentforge.core import brain_runner as _implementation
    sys.modules[__name__] = _implementation
