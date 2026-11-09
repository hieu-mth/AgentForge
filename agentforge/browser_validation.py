"""Legacy import alias; canonical module: agentforge.features.websites.browser_validation.

Exports the exact same live module for existing monkeypatches, DB state,
and product/workspace paths; no code or data is duplicated.
"""
if __name__ == "__main__":
    from agentforge.features.websites.browser_validation import main
    main()
else:
    import sys
    from agentforge.features.websites import browser_validation as _implementation
    sys.modules[__name__] = _implementation
