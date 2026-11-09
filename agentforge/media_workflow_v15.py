"""Legacy alias to agentforge.domains.media.workflow."""
if __name__ == "__main__":
    from agentforge.domains.media.workflow import main
    main()
else:
    import sys
    from agentforge.domains.media import workflow as _implementation
    sys.modules[__name__] = _implementation
