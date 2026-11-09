"""Compatibility alias; canonical source: agentforge.features.media.render."""
import sys
from agentforge.features.media import render as _implementation
sys.modules[__name__] = _implementation
