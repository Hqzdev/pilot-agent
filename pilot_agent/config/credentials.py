"""Credential helpers for env-first API keys.

Secrets live outside config parsing. Runtime resolution is:
environment variable -> credentials.yaml -> actionable error.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pilot_agent.config.schema import ProviderConfig, load_env_file

SERVICE_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "brave": "BRAVE_API_KEY",
    "vercel": "VERCEL_TOKEN",
}


@dataclass(frozen=True)
class CredentialResolution:
    service: str
    value: str | None
    source: str
    env_name: str
    path: Path


def load_local_env(home: Path | None = None) -> None:
    """Load `~/.pilot-agent/.env` style exports without overwriting real env vars."""

    load_env_file(home)


def require_api_key(config: ProviderConfig) -> str:
    """Return the provider API key or raise an actionable RuntimeError."""

    return config.resolve_key()


def credentials_path(home: Path) -> Path:
    return home / "credentials.yaml"


def credential_field(service: str) -> str:
    return "token" if service == "vercel" else "api_key"


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
    tmp.unlink(missing_ok=True)
    fd = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=True)
    tmp.replace(path)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return path


def service_env_var(service: str) -> str:
    return SERVICE_ENV_VARS.get(service, f"{service.upper()}_API_KEY")


def _credential_value(raw: Any, service: str) -> str | None:
    if isinstance(raw, str) and raw:
        return raw
    if isinstance(raw, dict):
        field = credential_field(service)
        value = raw.get(field) or raw.get("api_key") or raw.get("token")
        if isinstance(value, str) and value:
            return value
    return None


def resolve_credential(
    service: str,
    home: Path,
    *,
    env_name: str | None = None,
) -> CredentialResolution:
    load_local_env(home)
    primary_env = env_name or service_env_var(service)
    env_names = [primary_env]
    default_env = service_env_var(service)
    if default_env not in env_names:
        env_names.append(default_env)
    for candidate in env_names:
        value = os.environ.get(candidate)
        if value:
            return CredentialResolution(service, value, "env", candidate, credentials_path(home))
    raw = _read_credentials(home).get(service)
    value = _credential_value(raw, service)
    if value:
        return CredentialResolution(
            service,
            value,
            "credentials",
            primary_env,
            credentials_path(home),
        )
    return CredentialResolution(service, None, "missing", primary_env, credentials_path(home))


def get_credential(service: str, home: Path, *, env_name: str | None = None) -> str | None:
    return resolve_credential(service, home, env_name=env_name).value


def set_credential(service: str, value: str, home: Path) -> Path:
    data = _read_credentials(home)
    current = data.get(service)
    item = current if isinstance(current, dict) else {}
    item[credential_field(service)] = value
    data[service] = item
    return _write_credentials(home, data)


def remove_credential(service: str, home: Path) -> bool:
    data = _read_credentials(home)
    existed = service in data
    if existed:
        del data[service]
        _write_credentials(home, data)
    return existed


def credential_services(home: Path) -> list[str]:
    return sorted(str(key) for key in _read_credentials(home))


def credentials_permissions(home: Path) -> tuple[bool, str | None]:
    path = credentials_path(home)
    if not path.exists():
        return (True, None)
    mode = stat.S_IMODE(path.stat().st_mode)
    return (mode <= 0o600, oct(mode))


def mask_secret(value: str | None) -> str:
    if not value:
        return "not configured"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:6]}…{value[-4:]}"
