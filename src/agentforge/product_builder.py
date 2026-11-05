"""Legacy import alias; canonical module: agentforge.domains.websites.builder.

Exports the exact same live module for existing monkeypatches, DB state,
and product/workspace paths; no code or data is duplicated.
"""
if __name__ == "__main__":
    from agentforge.domains.websites.builder import main
    main()
else:
    import sys
    from agentforge.domains.websites import builder as _implementation
    sys.modules[__name__] = _implementation
