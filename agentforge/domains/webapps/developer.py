"""Compatibility module; use agentforge.features.webapps.developer for new code."""
if __name__ == "__main__":
    from agentforge.features.webapps.developer import main
    main()
else:
    import sys
    from agentforge.features.webapps import developer as _implementation
    sys.modules[__name__] = _implementation
