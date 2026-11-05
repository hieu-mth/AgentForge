"""Legacy alias to agentforge.domains.media.render."""
import sys
from agentforge.domains.media import render as _implementation
sys.modules[__name__] = _implementation
