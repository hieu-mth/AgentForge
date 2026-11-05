"""Compatibility wrapper; canonical module is agentforge.ai.worker_registry."""
from agentforge.ai.worker_registry import ROOT, WORKER_ID_PATTERN, ALLOWED_FIELDS, SUPPORTED_RUNTIMES, WorkerConfigError, load_worker

__all__ = ["ROOT","WORKER_ID_PATTERN","ALLOWED_FIELDS","SUPPORTED_RUNTIMES","WorkerConfigError","load_worker"]
