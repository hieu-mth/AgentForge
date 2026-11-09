"""Compatibility alias: implementation moved to agentforge.features.growth.store."""
import sys
from agentforge.features.growth import store as _implementation
sys.modules[__name__] = _implementation
