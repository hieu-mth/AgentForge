"""Compatibility module; canonical implementation: agentforge.features.websites.revision_context."""
import sys
from agentforge.features.websites import revision_context as _implementation
sys.modules[__name__] = _implementation
