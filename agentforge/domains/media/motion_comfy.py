"""Compatibility alias; canonical source: agentforge.features.film_studio.motion_comfy."""
if __name__ == "__main__":
    from agentforge.features.film_studio.motion_comfy import main
    main()
else:
    import sys
    from agentforge.features.film_studio import motion_comfy as _implementation
    sys.modules[__name__] = _implementation
