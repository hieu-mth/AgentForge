"""Legacy import alias; canonical module: agentforge.domains.websites.assets.

Exports the exact same live module for existing monkeypatches, DB state,
and product/workspace paths; no code or data is duplicated.
"""
if __name__ == "__main__":
    from agentforge.domains.websites.assets import main
    main()
else:
    import sys
    from agentforge.domains.websites import assets as _implementation
    sys.modules[__name__] = _implementation
