"""Legacy-friendly alias for the canonical webapp compiler module."""
if __name__ == "__main__":
    from agentforge.features.webapps.builder import main
    main()
else:
    import sys
    from agentforge.features.webapps import builder as implementation
    sys.modules[__name__] = implementation
