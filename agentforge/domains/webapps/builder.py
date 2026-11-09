"""Compatibility module; use agentforge.features.webapps.builder for new code."""
if __name__ == "__main__":
    from agentforge.features.webapps.builder import main
    main()
else:
    import sys
    from agentforge.features.webapps import builder as _implementation
    sys.modules[__name__] = _implementation
