"""Compatibility module; use agentforge.features.webapps.architect for new code."""
import sys
from agentforge.features.webapps import architect as _implementation
sys.modules[__name__] = _implementation
