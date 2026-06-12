from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from importlib import import_module
from typing import Protocol, TypeVar

from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential

from devagent.agent.types import CompletionResponse, Message, ToolSpec


class ProviderConfigLike(Protocol):
    provider: str
    model: str
    base_url: str | None

    def resolve_key(self) -> str: ...


P = TypeVar("P", bound="Provider")
_REGISTRY: dict[str, type[Provider]] = {}
_PROVIDER_MODULES = {
    "anthropic": "devagent.providers.anthropic",
    "openai": "devagent.providers.openai",
    "openrouter": "devagent.providers.openrouter",
}


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _is_timeout(exc: BaseException) -> bool:
    name = exc.__class__.__name__.lower()
    return "timeout" in name or "timedout" in name


def _retryable(exc: BaseException) -> bool:
    if _is_timeout(exc):
        return True
    return _status_code(exc) in {429, 500, 529}


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome is not None else None
    exc_name = exc.__class__.__name__ if exc else "error"
    sys.stderr.write(f"provider retry {state.attempt_number}/5 after {exc_name}\n")


class Provider(ABC):
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @retry(
        retry=retry_if_exception(_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        before_sleep=_log_retry,
        reraise=True,
    )
    def complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        return self._complete(system, messages, tools, max_tokens=max_tokens)

    @abstractmethod
    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse: ...

    @abstractmethod
    def count_tokens(self, system: str, messages: list[Message]) -> int: ...

    @property
    @abstractmethod
    def context_window(self) -> int: ...


def register(name: str) -> Callable[[type[P]], type[P]]:
    def deco(cls: type[P]) -> type[P]:
        _REGISTRY[name] = cls
        return cls

    return deco


def from_config(cfg: ProviderConfigLike) -> Provider:
    if cfg.provider not in _REGISTRY and cfg.provider in _PROVIDER_MODULES:
        import_module(_PROVIDER_MODULES[cfg.provider])
    try:
        provider_cls = _REGISTRY[cfg.provider]
    except KeyError as exc:
        known = ", ".join(sorted(_PROVIDER_MODULES)) or "(none)"
        raise ValueError(f"unknown provider {cfg.provider!r}; known providers: {known}") from exc
    return provider_cls(model=cfg.model, api_key=cfg.resolve_key(), base_url=cfg.base_url)


__all__ = ["Provider", "_PROVIDER_MODULES", "_REGISTRY", "from_config", "register"]
