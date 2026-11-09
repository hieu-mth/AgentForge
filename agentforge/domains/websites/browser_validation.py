"""Compatibility module; canonical implementation: agentforge.features.websites.browser_validation."""
if __name__ == "__main__":
    from agentforge.features.websites.browser_validation import main
    main()
else:
    import sys
    from agentforge.features.websites import browser_validation as _implementation
    sys.modules[__name__] = _implementation
