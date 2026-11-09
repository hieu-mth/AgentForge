"""Compatibility alias; canonical source: agentforge.features.film_studio.long_form."""
if __name__ == "__main__":
    from agentforge.features.film_studio.long_form import main
    main()
else:
    import sys
    from agentforge.features.film_studio import long_form as _implementation
    sys.modules[__name__] = _implementation
