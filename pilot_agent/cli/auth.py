"""Provider key, default model, validation, and model catalog helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from pydantic import BaseModel


class ModelInfo(BaseModel):
    provider: str
    name: str
    context_window: int
    input_price: float | None = None
    output_price: float | None = None
    supports_tools: bool = True


PROVIDER_KEY_ENVS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
PROVIDERS = tuple(PROVIDER_KEY_ENVS)

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5",
    "openrouter": "qwen/qwen3-coder",
}

STATIC_MODELS = {
    "anthropic": [
        ModelInfo(provider="anthropic", name="claude-sonnet-4-6", context_window=200_000),
        ModelInfo(provider="anthropic", name="claude-opus-4-1", context_window=200_000),
        ModelInfo(provider="anthropic", name="claude-haiku-4-5", context_window=200_000),
    ],
    "openai": [
        ModelInfo(provider="openai", name="gpt-5", context_window=400_000),
        ModelInfo(provider="openai", name="gpt-5-mini", context_window=400_000),
        ModelInfo(provider="openai", name="gpt-4.1", context_window=1_000_000),
    ],
    "openrouter": [
        ModelInfo(provider="openrouter", name="qwen/qwen3-coder", context_window=262_144),
        ModelInfo(provider="openrouter", name="anthropic/claude-sonnet-4", context_window=200_000),
        ModelInfo(provider="openrouter", name="openai/gpt-5", context_window=400_000),
    ],
}


@dataclass(frozen=True)
class ValidationResult:
    status: str
    details: str
    latency_ms: int | None = None


def provider_key_env(provider: str) -> str:
    try:
        return PROVIDER_KEY_ENVS[provider]
    except KeyError as exc:
        raise ValueError(f"unknown provider {provider!r}") from exc


def default_model(provider: str) -> str:
    try:
        return DEFAULT_MODELS[provider]
    except KeyError as exc:
        raise ValueError(f"unknown provider {provider!r}") from exc


def list_models(provider: str, *, api_key: str | None = None) -> list[ModelInfo]:
    if provider == "openrouter" and api_key:
        try:
            response = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            models = [
                ModelInfo(
                    provider="openrouter",
                    name=str(item["id"]),
                    context_window=int(item.get("context_length") or 128_000),
                    input_price=_price(item, "prompt"),
                    output_price=_price(item, "completion"),
                    supports_tools=_supports_tools(item),
                )
                for item in items
                if isinstance(item, dict) and item.get("id")
            ]
            tool_models = [model for model in models if model.supports_tools]
            return (tool_models or models)[:20] or STATIC_MODELS[provider]
        except Exception:
            return STATIC_MODELS[provider]
    try:
        return STATIC_MODELS[provider]
    except KeyError as exc:
        raise ValueError(f"unknown provider {provider!r}") from exc


def validate_provider_key(
    provider: str,
    api_key: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
    timeout_s: float = 5.0,
) -> ValidationResult:
    start = time.monotonic()
    try:
        if provider == "anthropic":
            response = requests.post(
                (base_url or "https://api.anthropic.com") + "/v1/messages/count_tokens",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model or default_model(provider),
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=timeout_s,
            )
        elif provider == "openai":
            response = requests.get(
                (base_url or "https://api.openai.com/v1") + "/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout_s,
            )
        elif provider == "openrouter":
            response = requests.get(
                (base_url or "https://openrouter.ai/api/v1") + "/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout_s,
            )
        else:
            raise ValueError(f"unknown provider {provider!r}")
    except requests.RequestException as exc:
        return ValidationResult("warn", f"live API check skipped: {exc.__class__.__name__}")
    latency = int((time.monotonic() - start) * 1000)
    if response.status_code in {401, 403}:
        return ValidationResult("fail", response.text[:200] or response.reason, latency)
    if response.status_code >= 400:
        return ValidationResult("warn", f"API returned HTTP {response.status_code}", latency)
    return ValidationResult("pass", "live API call passed", latency)


def _supports_tools(item: dict[str, object]) -> bool:
    raw = item.get("supported_parameters")
    if isinstance(raw, list):
        return "tools" in {str(value) for value in raw}
    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        tokenizer = architecture.get("tokenizer")
        return bool(tokenizer)
    return True


def _price(item: dict[str, object], key: str) -> float | None:
    pricing = item.get("pricing")
    if not isinstance(pricing, dict):
        return None
    raw = pricing.get(key)
    try:
        return float(str(raw)) * 1_000_000
    except (TypeError, ValueError):
        return None
