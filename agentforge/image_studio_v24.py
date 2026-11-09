"""Legacy alias for agentforge.features.websites.image_studio."""
import sys
from agentforge.features.websites import image_studio as _implementation
sys.modules[__name__] = _implementation
