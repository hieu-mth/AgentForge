"""Compatibility module; canonical implementation: agentforge.features.websites.builder."""
if __name__ == "__main__":
    from agentforge.features.websites.builder import main
    main()
else:
    import sys
    from agentforge.features.websites import builder as _implementation
    sys.modules[__name__] = _implementation
