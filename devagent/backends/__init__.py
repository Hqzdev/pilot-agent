"""Execution backends for agent-owned shell commands."""

from devagent.backends.base import BackendCheckResult, ExecResult, ExecutionBackend, ProcessHandle
from devagent.backends.factory import backend_from_config

__all__ = [
    "BackendCheckResult",
    "ExecResult",
    "ExecutionBackend",
    "ProcessHandle",
    "backend_from_config",
]
