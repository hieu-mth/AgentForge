"""Compatibility module; use agentforge.features.webapps.syntax for new code."""
import sys
from agentforge.features.webapps import syntax as _implementation
sys.modules[__name__] = _implementation
