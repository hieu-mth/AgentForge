"""Compatibility alias: implementation moved to agentforge.features.growth.bundle."""
import sys
from agentforge.features.growth import bundle as _implementation
sys.modules[__name__] = _implementation
