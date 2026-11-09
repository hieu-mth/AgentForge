"""Compatibility module; use agentforge.features.webapps.toolchain for new code."""
import sys
from agentforge.features.webapps import toolchain as _implementation
sys.modules[__name__] = _implementation
