from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from pilot_agent.gateway.core import GatewayEvent

MAX_MESSAGE_CHARS = 4096


class TelegramAdapter:
    def __init__(
        self,
        token: str,
        *,
        poll_timeout_s: int = 30,
    ):
        self.token = token
        self.client = httpx.Client(timeout=poll_timeout_s + 5)
        self.poll_timeout_s = poll_timeout_s
        self.offset: int | None = None

    @classmethod
    def from_env(cls, token_env: str, *, poll_timeout_s: int = 30) -> TelegramAdapter:
        token = os.environ.get(token_env)
        if not token:
            raise RuntimeError(f"Telegram token missing. Set {token_env}.")
        return cls(token, poll_timeout_s=poll_timeout_s)

    def poll_events(self) -> list[GatewayEvent]:
        payload: dict[str, Any] = {"timeout": self.poll_timeout_s, "allowed_updates": ["message"]}
        if self.offset is not None:
            payload["offset"] = self.offset
        data = self._post("getUpdates", payload)
        updates = data.get("result", [])
        events: list[GatewayEvent] = []
        for update in updates if isinstance(updates, list) else []:
            if isinstance(update, dict):
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    self.offset = update_id + 1
                event = normalize_update(update)
                if event is not None:
                    events.append(event)
        return events

    def send_text(self, chat_id: str, text: str) -> None:
        for chunk in chunk_text(text):
            self._post("sendMessage", {"chat_id": chat_id, "text": chunk})

    def _post(self, method: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            f"https://api.telegram.org/bot{self.token}/{method}",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise RuntimeError(f"Telegram API call failed: {method}")
        return data


def normalize_update(update: Mapping[str, Any]) -> GatewayEvent | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    text = message.get("text")
    sender = message.get("from")
    chat = message.get("chat")
    update_id = update.get("update_id")
    if not isinstance(text, str) or not isinstance(sender, dict) or not isinstance(chat, dict):
        return None
    user_id = sender.get("id")
    chat_id = chat.get("id")
    if user_id is None or chat_id is None or update_id is None:
        return None
    return GatewayEvent(
        platform="telegram",
        event_id=str(update_id),
        chat_id=str(chat_id),
        user_id=str(user_id),
        text=text,
    )


def chunk_text(text: str) -> list[str]:
    if not text:
        return [""]
    step = MAX_MESSAGE_CHARS
    return [text[start : start + step] for start in range(0, len(text), step)]
