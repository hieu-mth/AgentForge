"""Stable CLI module alias for isolated application QA."""
if __name__ == "__main__":
    from agentforge.features.webapps.sandbox import main
    main()
else:
    import sys
    from agentforge.features.webapps import sandbox as implementation
    sys.modules[__name__] = implementation
