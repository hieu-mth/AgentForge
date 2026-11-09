"""Compatibility wrapper; canonical module is agentforge.ai.model_registry."""
from agentforge.ai.model_registry import ROOT, DEFAULT_CONFIG, ENV_NAME, ModelConfigError, load_models

__all__ = ["ROOT","DEFAULT_CONFIG","ENV_NAME","ModelConfigError","load_models"]
