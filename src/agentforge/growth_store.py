"""Legacy alias to agentforge.domains.growth.store."""
import sys
from agentforge.domains.growth import store as _implementation
sys.modules[__name__] = _implementation
