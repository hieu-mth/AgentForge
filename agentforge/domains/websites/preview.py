"""Compatibility module; canonical implementation: agentforge.features.websites.preview."""
import sys
from agentforge.features.websites import preview as _implementation
sys.modules[__name__] = _implementation
