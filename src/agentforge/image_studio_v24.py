"""Legacy alias for agentforge.domains.websites.image_studio."""
import sys
from agentforge.domains.websites import image_studio as _implementation
sys.modules[__name__] = _implementation
