"""Legacy alias to agentforge.domains.growth.bundle."""
import sys
from agentforge.domains.growth import bundle as _implementation
sys.modules[__name__] = _implementation
