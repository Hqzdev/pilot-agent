from __future__ import annotations

import logging
from typing import Any

import openai
import requests

from pilot_agent.providers.base import register
from pilot_agent.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)
_MODEL_CACHE: dict[str, int] = {}
_HEADERS = {"HTTP-Referer": "https://github.com/Hqzdev/pilot-agent", "X-Title": "Pilot Agent"}


@register("openrouter")
class OpenRouterProvider(OpenAIProvider):
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        url = base_url or self.BASE_URL
        super().__init__(model=model, api_key=api_key, base_url=url)
        self.client = openai.OpenAI(api_key=api_key, base_url=url, default_headers=_HEADERS)

    @property
    def context_window(self) -> int:
        if self.model in _MODEL_CACHE:
            return _MODEL_CACHE[self.model]
        try:
            data: dict[str, Any] = requests.get(f"{self.BASE_URL}/models", timeout=5).json()
            _MODEL_CACHE[self.model] = next(
                int(item.get("context_length", 128_000))
                for item in data.get("data", [])
                if item.get("id") == self.model
            )
        except Exception as exc:
            logger.warning("OpenRouter model metadata unavailable: %s", exc)
            _MODEL_CACHE[self.model] = 128_000
        return _MODEL_CACHE[self.model]
