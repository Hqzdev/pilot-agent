"""Factory for execution backends selected by config."""

from __future__ import annotations

from pathlib import Path

from devagent.backends.base import ExecutionBackend
from devagent.backends.docker import DockerBackend
from devagent.backends.local import LocalBackend
from devagent.config.schema import DevAgentConfig


def backend_from_config(cfg: DevAgentConfig, project_root: Path) -> ExecutionBackend:
    if cfg.backend == "docker":
        return DockerBackend(
            project_root=project_root,
            image=cfg.sandbox.image,
            network=cfg.sandbox.network,
        )
    return LocalBackend()
