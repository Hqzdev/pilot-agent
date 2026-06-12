"""Provider key, default model, and model catalog helpers for CLI onboarding."""

from __future__ import annotations

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
                )
                for item in items
                if isinstance(item, dict) and item.get("id")
            ]
            return models[:20] or STATIC_MODELS[provider]
        except Exception:
            return STATIC_MODELS[provider]
    try:
        return STATIC_MODELS[provider]
    except KeyError as exc:
        raise ValueError(f"unknown provider {provider!r}") from exc
