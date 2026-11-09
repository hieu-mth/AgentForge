"""Compatibility alias; canonical source: agentforge.features.media.quality."""
import sys
from agentforge.features.media import quality as _implementation
sys.modules[__name__] = _implementation
