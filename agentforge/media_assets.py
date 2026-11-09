"""Legacy alias to agentforge.features.media.assets."""
import sys
from agentforge.features.media import assets as _implementation
sys.modules[__name__] = _implementation
