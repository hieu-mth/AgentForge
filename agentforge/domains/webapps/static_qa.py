"""Compatibility module; use agentforge.features.webapps.static_qa for new code."""
import sys
from agentforge.features.webapps import static_qa as _implementation
sys.modules[__name__] = _implementation
