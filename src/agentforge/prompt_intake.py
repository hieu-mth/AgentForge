"""Backward-compatible import for prompt intake; canonical module is agentforge.ai.prompt_intake."""
from agentforge.ai.prompt_intake import MAX_PROMPT, _fold, plan_request

__all__ = ["MAX_PROMPT", "plan_request"]
