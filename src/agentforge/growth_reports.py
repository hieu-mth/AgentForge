"""Legacy alias to agentforge.domains.growth.reports."""
import sys
from agentforge.domains.growth import reports as _implementation
sys.modules[__name__] = _implementation
