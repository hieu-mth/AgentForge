"""Legacy import alias; canonical module: agentforge.domains.websites.revision.

Exports the exact same live module for existing monkeypatches, DB state,
and product/workspace paths; no code or data is duplicated.
"""
if __name__ == "__main__":
    from agentforge.domains.websites.revision import main
    main()
else:
    import sys
    from agentforge.domains.websites import revision as _implementation
    sys.modules[__name__] = _implementation
