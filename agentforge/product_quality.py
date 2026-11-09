"""Legacy import alias; canonical module: agentforge.features.websites.quality.

Exports the exact same live module for existing monkeypatches, DB state,
and product/workspace paths; no code or data is duplicated.
"""
import sys
from agentforge.features.websites import quality as _implementation
sys.modules[__name__] = _implementation
