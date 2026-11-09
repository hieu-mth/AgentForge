"""Compatibility module; canonical implementation: agentforge.features.websites.design_kit."""
import sys
from agentforge.features.websites import design_kit as _implementation
sys.modules[__name__] = _implementation
