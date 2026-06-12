from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

RECOMMENDED: dict[str, dict[str, str]] = {
    "provider": {
        "value": "anthropic",
        "label": "Anthropic",
        "reason": "best tool calling for an agentic CLI",
    },
    "backend": {
        "value": "docker",
        "label": "Docker sandbox",
        "reason": "agent commands are isolated from your system",
    },
    "tools.web_search.provider": {
        "value": "tavily",
        "label": "Tavily",
        "reason": "LLM-friendly responses and a generous free tier",
    },
}


def recommended_value(key: str) -> str:
    return RECOMMENDED[key]["value"]


def recommended_label(key: str) -> str:
    item = RECOMMENDED[key]
    return f"{item['label']} (recommended) - {item['reason']}"


class DeployConfig(BaseModel):
    enabled: bool = True
    vercel_token_env: str = "VERCEL_TOKEN"


class MarketingConfig(BaseModel):
    enabled: bool = True


class PhasesConfig(BaseModel):
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    marketing: MarketingConfig = Field(default_factory=MarketingConfig)


class UIConfig(BaseModel):
    color: Literal["auto", "always", "never"] = "auto"
    show_token_counter: bool = True


class SandboxConfig(BaseModel):
    image: str = "pilot-agent-sandbox:latest"
    network: Literal["bridge", "none"] = "bridge"


class WebSearchConfig(BaseModel):
    enabled: bool = True
    provider: Literal["tavily", "brave", "searxng"] = "tavily"
    max_results: int = 5
    searxng_url: str | None = None


class WebFetchConfig(BaseModel):
    enabled: bool = False


class DeployToolConfig(BaseModel):
    enabled: bool = True


class ToolsConfig(BaseModel):
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    web_fetch: WebFetchConfig = Field(default_factory=WebFetchConfig)
    deploy: DeployToolConfig = Field(default_factory=DeployToolConfig)


class ProviderConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"
    base_url: str | None = None

    def resolve_key(self) -> str:
        from pilot_agent.config.credentials import resolve_credential

        resolved = resolve_credential(self.provider, default_home(), env_name=self.api_key_env)
        if not resolved.value:
            raise RuntimeError(
                f"API key not found for {self.provider}. "
                f"Run: pilot-agent auth set {self.provider}"
            )
        return resolved.value


class PilotAgentConfig(ProviderConfig):
    backend: Literal["docker", "local"] = "docker"
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    summarizer_model: str | None = None
    budget_ratio: float = 0.7
    max_turns: int = 200
    tool_timeout_s: int = 120
    phases: PhasesConfig = Field(default_factory=PhasesConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    sources: dict[str, str] = Field(default_factory=dict)


DEFAULTS_PATH = Path(__file__).with_name("defaults.yaml")


def default_home() -> Path:
    return Path(os.environ.get("PILOT_AGENT_HOME", "~/.pilot-agent")).expanduser()


DEFAULT_HOME = default_home()


def load_env_file(home: Path | None = None) -> None:
    path = (home or default_home()) / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if clean.startswith("export "):
            clean = clean.removeprefix("export ").strip()
        if "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def user_config_path(home: Path | None = None) -> Path:
    return (home or default_home()) / "config.yaml"


def project_config_path(project_root: Path | None = None) -> Path:
    return (project_root or Path(".")).resolve() / ".pilot-agent" / "config.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _deep_merge(target: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def _mark_sources(sources: dict[str, str], data: dict[str, Any], source: str) -> None:
    for key in _flatten(data):
        sources[key] = source


def _env_map() -> dict[str, str]:
    return {
        "provider": "PILOT_AGENT_PROVIDER",
        "model": "PILOT_AGENT_MODEL",
        "api_key_env": "PILOT_AGENT_API_KEY_ENV",
        "base_url": "PILOT_AGENT_BASE_URL",
        "backend": "PILOT_AGENT_BACKEND",
        "sandbox.image": "PILOT_AGENT_SANDBOX_IMAGE",
        "sandbox.network": "PILOT_AGENT_SANDBOX_NETWORK",
        "summarizer_model": "PILOT_AGENT_SUMMARIZER_MODEL",
        "budget_ratio": "PILOT_AGENT_BUDGET_RATIO",
        "max_turns": "PILOT_AGENT_MAX_TURNS",
        "tool_timeout_s": "PILOT_AGENT_TOOL_TIMEOUT_S",
        "phases.deploy.enabled": "PILOT_AGENT_PHASES_DEPLOY_ENABLED",
        "phases.deploy.vercel_token_env": "PILOT_AGENT_PHASES_DEPLOY_VERCEL_TOKEN_ENV",
        "phases.marketing.enabled": "PILOT_AGENT_PHASES_MARKETING_ENABLED",
        "tools.web_search.enabled": "PILOT_AGENT_TOOLS_WEB_SEARCH_ENABLED",
        "tools.web_search.provider": "PILOT_AGENT_TOOLS_WEB_SEARCH_PROVIDER",
        "tools.web_search.max_results": "PILOT_AGENT_TOOLS_WEB_SEARCH_MAX_RESULTS",
        "tools.web_search.searxng_url": "PILOT_AGENT_TOOLS_WEB_SEARCH_SEARXNG_URL",
        "tools.web_fetch.enabled": "PILOT_AGENT_TOOLS_WEB_FETCH_ENABLED",
        "tools.deploy.enabled": "PILOT_AGENT_TOOLS_DEPLOY_ENABLED",
        "ui.color": "PILOT_AGENT_UI_COLOR",
        "ui.show_token_counter": "PILOT_AGENT_UI_SHOW_TOKEN_COUNTER",
    }


def _coerce_raw(value: str) -> Any:
    loaded = yaml.safe_load(value)
    return value if loaded is None and value.lower() != "null" else loaded


def _set_nested(data: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    cursor = data
    for part in parts[:-1]:
        next_value = cursor.setdefault(part, {})
        if not isinstance(next_value, dict):
            raise ValueError(f"cannot set nested key under scalar: {part}")
        cursor = next_value
    cursor[parts[-1]] = value


def _get_nested(data: dict[str, Any], key: str) -> Any:
    cursor: Any = data
    for part in key.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise KeyError(key)
        cursor = cursor[part]
    return cursor


def _model_data(cfg: PilotAgentConfig) -> dict[str, Any]:
    data = cfg.model_dump(exclude={"sources"})
    return data


def flatten_config(cfg: PilotAgentConfig) -> dict[str, Any]:
    return _flatten(_model_data(cfg))


def load_config(
    *,
    provider: str | None = None,
    model: str | None = None,
    home: Path | None = None,
    project_root: Path | None = None,
    config_path: Path | None = None,
) -> PilotAgentConfig:
    home = home or default_home()
    load_env_file(home)
    data = _load_yaml(DEFAULTS_PATH)
    sources: dict[str, str] = dict.fromkeys(_flatten(data), "defaults")
    if config_path is not None:
        override = _load_yaml(config_path)
        _deep_merge(data, override)
        _mark_sources(sources, override, str(config_path))
    else:
        user_path = user_config_path(home)
        user_config = _load_yaml(user_path)
        _deep_merge(data, user_config)
        _mark_sources(sources, user_config, "user")
        project_path = project_config_path(project_root)
        project_config = _load_yaml(project_path)
        _deep_merge(data, project_config)
        _mark_sources(sources, project_config, "project")
    for key, env_name in _env_map().items():
        if os.environ.get(env_name) is not None:
            _set_nested(data, key, _coerce_raw(os.environ[env_name]))
            sources[key] = "env"
    if provider is not None:
        data["provider"] = provider
        sources["provider"] = "cli"
    if model is not None:
        data["model"] = model
        sources["model"] = "cli"
    cfg = PilotAgentConfig(**data)
    cfg.sources = sources
    return cfg


def config_value(cfg: PilotAgentConfig, key: str) -> Any:
    return _get_nested(_model_data(cfg), key)


def write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)


def set_config_value(path: Path, key: str, raw_value: str) -> PilotAgentConfig:
    current = _load_yaml(path)
    candidate = dict(current)
    _set_nested(candidate, key, _coerce_raw(raw_value))
    merged = _load_yaml(DEFAULTS_PATH)
    _deep_merge(merged, candidate)
    PilotAgentConfig(**merged)
    write_yaml_atomic(path, candidate)
    return load_config(config_path=path)


def update_config_values(path: Path, updates: dict[str, Any]) -> PilotAgentConfig:
    current = _load_yaml(path)
    candidate = dict(current)
    for key, value in updates.items():
        _set_nested(candidate, key, value)
    merged = _load_yaml(DEFAULTS_PATH)
    _deep_merge(merged, candidate)
    PilotAgentConfig(**merged)
    write_yaml_atomic(path, candidate)
    return load_config(config_path=path)
