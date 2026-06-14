from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pilot_agent.config.schema import PilotAgentConfig


@dataclass(frozen=True)
class GatewayEvent:
    platform: str
    event_id: str
    chat_id: str
    user_id: str
    text: str


class GatewayAdapter(Protocol):
    def poll_events(self) -> list[GatewayEvent]: ...

    def send_text(self, chat_id: str, text: str) -> None: ...


def parse_allowed_users(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


@dataclass(frozen=True)
class GatewayAuthorizer:
    allowed_users: set[str]
    allow_all: bool = False

    def is_allowed(self, event: GatewayEvent) -> bool:
        return self.allow_all or event.user_id in self.allowed_users


def authorizer_from_config(
    cfg: PilotAgentConfig,
    environ: Mapping[str, str] | None = None,
) -> GatewayAuthorizer:
    env = environ or os.environ
    return GatewayAuthorizer(
        allowed_users=parse_allowed_users(env.get(cfg.gateway.telegram_allowed_users_env)),
        allow_all=_truthy(env.get(cfg.gateway.allow_all_users_env)),
    )


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}
