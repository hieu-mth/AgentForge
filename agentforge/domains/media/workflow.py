"""Compatibility alias; canonical source: agentforge.features.media.workflow."""
if __name__ == "__main__":
    from agentforge.features.media.workflow import main
    main()
else:
    import sys
    from agentforge.features.media import workflow as _implementation
    sys.modules[__name__] = _implementation
