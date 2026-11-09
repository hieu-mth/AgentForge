"""Compatibility alias for the canonical agentforge.core.task_history module.

Aliases rather than duplicated imports preserve existing monkeypatching,
module-level DB constants, and all legacy CLI entrypoints.
"""
if __name__ == "__main__":
    from agentforge.core.task_history import main
    main()
else:
    import sys
    from agentforge.core import task_history as _implementation
    sys.modules[__name__] = _implementation
