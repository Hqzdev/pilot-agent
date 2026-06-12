"""Execution backends for agent-owned shell commands."""

from pilot_agent.backends.base import (
    BackendCheckResult,
    ExecResult,
    ExecutionBackend,
    ProcessHandle,
)
from pilot_agent.backends.factory import backend_from_config

__all__ = [
    "BackendCheckResult",
    "ExecResult",
    "ExecutionBackend",
    "ProcessHandle",
    "backend_from_config",
]
