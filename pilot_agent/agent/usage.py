from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class CanonicalUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    request_count: int = 1

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens


@dataclass
class SessionUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    request_count: int = 0
    cost_usd: Decimal | None = Decimal("0")

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    def add(self, usage: CanonicalUsage, *, provider: str = "", model: str = "") -> Decimal | None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_tokens += usage.cache_read_tokens
        self.cache_write_tokens += usage.cache_write_tokens
        self.reasoning_tokens += usage.reasoning_tokens
        self.request_count += usage.request_count
        cost = estimate_cost(provider, model, usage)
        if self.cost_usd is not None and cost is not None:
            self.cost_usd += cost
        else:
            self.cost_usd = None
        return cost

    def summary(self) -> str:
        cost = "unknown" if self.cost_usd is None else f"${self.cost_usd:.4f}"
        return (
            f"requests: {self.request_count}\n"
            f"input tokens: {self.input_tokens}\n"
            f"output tokens: {self.output_tokens}\n"
            f"cache read/write: {self.cache_read_tokens}/{self.cache_write_tokens}\n"
            f"reasoning tokens: {self.reasoning_tokens}\n"
            f"total tokens: {self.total_tokens}\n"
            f"estimated cost: {cost}"
        )


def normalize_usage(raw: dict[str, Any] | None) -> CanonicalUsage:
    if not raw:
        return CanonicalUsage(request_count=0)
    prompt_total = _int(raw.get("input_tokens", raw.get("prompt_tokens", 0)))
    output_tokens = _int(raw.get("output_tokens", raw.get("completion_tokens", 0)))
    cache_read = _int(raw.get("cache_read_tokens", raw.get("cache_read_input_tokens", 0)))
    cache_write = _int(raw.get("cache_write_tokens", raw.get("cache_creation_input_tokens", 0)))
    input_tokens = max(0, prompt_total - cache_read - cache_write)
    return CanonicalUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_tokens=_int(raw.get("reasoning_tokens", 0)),
        request_count=1,
    )


def estimate_cost(provider: str, model: str, usage: CanonicalUsage) -> Decimal | None:
    pricing = _pricing(provider, model)
    if pricing is None:
        return None
    input_cost, output_cost = pricing
    million = Decimal(1_000_000)
    return (
        Decimal(usage.input_tokens + usage.cache_write_tokens) * input_cost / million
        + Decimal(usage.cache_read_tokens) * input_cost * Decimal("0.1") / million
        + Decimal(usage.output_tokens) * output_cost / million
    )


def _pricing(provider: str, model: str) -> tuple[Decimal, Decimal] | None:
    key = (provider.lower(), model.lower())
    if key[0] == "anthropic" and "sonnet" in key[1]:
        return Decimal("3"), Decimal("15")
    if key[0] == "anthropic" and "opus" in key[1]:
        return Decimal("15"), Decimal("75")
    if key[0] == "openai" and "gpt-5-mini" in key[1]:
        return Decimal("0.25"), Decimal("2")
    if key[0] == "openai" and "gpt-5" in key[1]:
        return Decimal("1.25"), Decimal("10")
    return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
