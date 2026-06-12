"""Credential helpers for env-first API keys.

This module keeps secret handling separate from config parsing: config stores
tool/provider choices, while runtime code resolves values from env or the
user-controlled credentials file in `~/.devagent/credentials.yaml`.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import yaml

from devagent.config.schema import ProviderConfig, load_env_file

SERVICE_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "brave": "BRAVE_API_KEY",
    "vercel": "VERCEL_TOKEN",
}


def load_local_env(home: Path | None = None) -> None:
    """Load `~/.devagent/.env` style exports without overwriting real env vars."""

    load_env_file(home)


def require_api_key(config: ProviderConfig) -> str:
    """Return the provider API key or raise an actionable RuntimeError."""

    return config.resolve_key()


def credentials_path(home: Path) -> Path:
    return home / "credentials.yaml"


def _read_credentials(home: Path) -> dict[str, Any]:
    path = credentials_path(home)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_credentials(home: Path, data: dict[str, Any]) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = credentials_path(home)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return path


def service_env_var(service: str) -> str:
    return SERVICE_ENV_VARS.get(service, f"{service.upper()}_API_KEY")


def get_credential(service: str, home: Path) -> str | None:
    env_name = service_env_var(service)
    value = os.environ.get(env_name)
    if value:
        return value
    raw = _read_credentials(home).get(service)
    if isinstance(raw, str) and raw:
        return raw
    return None


def set_credential(service: str, value: str, home: Path) -> Path:
    data = _read_credentials(home)
    data[service] = value
    return _write_credentials(home, data)


def mask_secret(value: str | None) -> str:
    if not value:
        return "not configured"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:6]}…{value[-4:]}"
