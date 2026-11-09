"""Compatibility module; canonical implementation: agentforge.features.websites.assets."""
if __name__ == "__main__":
    from agentforge.features.websites.assets import main
    main()
else:
    import sys
    from agentforge.features.websites import assets as _implementation
    sys.modules[__name__] = _implementation
