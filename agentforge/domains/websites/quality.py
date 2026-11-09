"""Compatibility module; canonical implementation: agentforge.features.websites.quality."""
import sys
from agentforge.features.websites import quality as _implementation
sys.modules[__name__] = _implementation
