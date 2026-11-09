"""Stable CLI module alias for isolated application QA."""
if __name__ == "__main__":
    from agentforge.domains.webapps.sandbox import main
    main()
else:
    import sys
    from agentforge.domains.webapps import sandbox as implementation
    sys.modules[__name__] = implementation
