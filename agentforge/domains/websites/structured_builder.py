"""Compatibility module; canonical implementation: agentforge.features.websites.structured_builder."""
import sys
from agentforge.features.websites import structured_builder as _implementation
sys.modules[__name__] = _implementation
