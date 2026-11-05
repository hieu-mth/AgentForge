"""Legacy alias to agentforge.domains.media.assets."""
import sys
from agentforge.domains.media import assets as _implementation
sys.modules[__name__] = _implementation
