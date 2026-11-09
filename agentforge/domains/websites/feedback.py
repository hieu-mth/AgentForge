"""Compatibility module; canonical implementation: agentforge.features.websites.feedback."""
import sys
from agentforge.features.websites import feedback as _implementation
sys.modules[__name__] = _implementation
