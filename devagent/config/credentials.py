"""Credential helpers for env-only API keys.

This module keeps secret handling separate from config parsing: config stores
only env-var names, while runtime code resolves values from the environment.
"""

from pathlib import Path

from devagent.config.schema import ProviderConfig, load_env_file


def load_local_env(home: Path | None = None) -> None:
    """Load `~/.devagent/.env` style exports without overwriting real env vars."""

    load_env_file(home)


def require_api_key(config: ProviderConfig) -> str:
    """Return the provider API key or raise an actionable RuntimeError."""

    return config.resolve_key()
