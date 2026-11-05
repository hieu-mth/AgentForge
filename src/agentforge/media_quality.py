"""Legacy alias to agentforge.domains.media.quality."""
import sys
from agentforge.domains.media import quality as _implementation
sys.modules[__name__] = _implementation
