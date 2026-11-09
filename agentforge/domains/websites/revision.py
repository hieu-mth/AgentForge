"""Compatibility module; canonical implementation: agentforge.features.websites.revision."""
if __name__ == "__main__":
    from agentforge.features.websites.revision import main
    main()
else:
    import sys
    from agentforge.features.websites import revision as _implementation
    sys.modules[__name__] = _implementation
