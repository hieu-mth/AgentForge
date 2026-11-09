"""Stable CLI alias for experimental unexecuted AI React proposals."""
if __name__ == "__main__":
    from agentforge.features.webapps.developer import main
    main()
else:
    import sys
    from agentforge.features.webapps import developer as implementation
    sys.modules[__name__] = implementation
