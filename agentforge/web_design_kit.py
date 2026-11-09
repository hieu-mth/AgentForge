"""Legacy import alias; canonical module: agentforge.features.websites.design_kit.

Exports the exact same live module for existing monkeypatches, DB state,
and product/workspace paths; no code or data is duplicated.
"""
import sys
from agentforge.features.websites import design_kit as _implementation
sys.modules[__name__] = _implementation
