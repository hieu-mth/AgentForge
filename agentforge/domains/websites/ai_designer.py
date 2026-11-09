"""Compatibility module; canonical implementation: agentforge.features.websites.ai_designer."""
import sys
from agentforge.features.websites import ai_designer as _implementation
sys.modules[__name__] = _implementation
