"""Compatibility alias: implementation moved to agentforge.features.growth.reports."""
import sys
from agentforge.features.growth import reports as _implementation
sys.modules[__name__] = _implementation
