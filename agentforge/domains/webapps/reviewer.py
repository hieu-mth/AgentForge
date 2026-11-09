"""Compatibility module; use agentforge.features.webapps.reviewer for new code."""
import sys
from agentforge.features.webapps import reviewer as _implementation
sys.modules[__name__] = _implementation
