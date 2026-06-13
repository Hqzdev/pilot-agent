from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderErrorInfo:
    kind: str
    message: str
    fix: str
    retryable: bool = False


def classify_provider_error(exc: BaseException, *, provider: str, model: str) -> ProviderErrorInfo:
    status = _status_code(exc)
    text = str(exc)
    lower = text.lower()

    if status in {401, 403} or "invalid api key" in lower or "authentication" in lower:
        return ProviderErrorInfo(
            "auth",
            f"{provider} authentication failed.",
            f"Run: pilot-agent auth set {provider}",
        )
    if status == 404 or "model" in lower and ("not found" in lower or "does not exist" in lower):
        return ProviderErrorInfo(
            "model",
            f"Model not found or unavailable: {model}",
            "Run: pilot-agent model",
        )
    if status == 429 or "rate limit" in lower:
        return ProviderErrorInfo(
            "rate_limit",
            "Provider rate limit reached.",
            "Wait for the provider limit to reset, or run: pilot-agent model",
            retryable=True,
        )
    if status in {402} or "billing" in lower or "insufficient" in lower or "quota" in lower:
        return ProviderErrorInfo(
            "billing",
            f"{provider} billing or quota blocked the request.",
            f"Check your {provider} account billing, or run: pilot-agent model",
        )
    if status in {400, 413} and ("context" in lower or "token" in lower or "too long" in lower):
        return ProviderErrorInfo(
            "context",
            "The request exceeded the model context window.",
            "Run /compact, choose a larger context model with /model, or reduce STATE.md.",
        )
    if status in {500, 502, 503, 504, 529}:
        return ProviderErrorInfo(
            "server",
            f"{provider} server error.",
            "Retry later, or run: pilot-agent model",
            retryable=True,
        )
    if _is_timeout(exc):
        return ProviderErrorInfo(
            "timeout",
            f"{provider} request timed out.",
            "Retry, or set a smaller task/context before continuing.",
            retryable=True,
        )
    return ProviderErrorInfo(
        "unknown",
        f"{provider} request failed: {text}",
        "Run: pilot-agent doctor",
    )


def format_provider_error(exc: BaseException, *, provider: str, model: str) -> str:
    info = classify_provider_error(exc, provider=provider, model=model)
    return f"{info.message} {info.fix}"


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
