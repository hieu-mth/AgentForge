"""Compatibility module; use agentforge.features.webapps.sandbox for new code."""
if __name__ == "__main__":
    from agentforge.features.webapps.sandbox import main
    main()
else:
    import sys
    from agentforge.features.webapps import sandbox as _implementation
    sys.modules[__name__] = _implementation
