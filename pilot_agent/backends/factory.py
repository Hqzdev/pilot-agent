"""Factory for execution backends selected by config."""

from __future__ import annotations

from pathlib import Path

from pilot_agent.backends.base import ExecutionBackend
from pilot_agent.backends.docker import DockerBackend
from pilot_agent.backends.local import LocalBackend
from pilot_agent.config.schema import PilotAgentConfig


def backend_from_config(cfg: PilotAgentConfig, project_root: Path) -> ExecutionBackend:
    if cfg.backend == "docker":
        return DockerBackend(
            project_root=project_root,
            image=cfg.sandbox.image,
            network=cfg.sandbox.network,
        )
    return LocalBackend()
