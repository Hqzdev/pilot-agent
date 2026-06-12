from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast

import anthropic

from pilot_agent.agent.types import CompletionResponse, Message, Role, ToolCall, ToolSpec
from pilot_agent.providers.base import Provider, register

logger = logging.getLogger(__name__)

_KNOWN_CONTEXT_WINDOWS = {
    "claude-opus-4-1": 200_000,
    "claude-opus-4-1-20250805": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-3-7-sonnet-latest": 200_000,
    "claude-3-5-sonnet-latest": 200_000,
    "claude-3-5-haiku-latest": 200_000,
}


def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type", ""))
    return str(getattr(block, "type", ""))


def _block_get(block: Any, name: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def anthropic_tools(tools: Iterable[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }
        for tool in tools
    ]


def anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    idx = 0
    while idx < len(messages):
        message = messages[idx]
        if message.role is Role.SYSTEM:
            idx += 1
            continue
        if message.role is Role.TOOL:
            blocks: list[dict[str, Any]] = []
            while idx < len(messages) and messages[idx].role is Role.TOOL:
                for result in messages[idx].tool_results:
                    block: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": result.tool_call_id,
                        "content": result.content,
                    }
                    if result.is_error:
                        block["is_error"] = True
                    blocks.append(block)
                idx += 1
            converted.append({"role": "user", "content": blocks})
            continue
        if message.role is Role.ASSISTANT:
            blocks = []
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            blocks.extend(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
                for call in message.tool_calls
            )
            converted.append({"role": "assistant", "content": blocks or message.content})
            idx += 1
            continue
        converted.append({"role": "user", "content": message.content})
        idx += 1
    return converted


def parse_anthropic_response(response: Any) -> CompletionResponse:
    content_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in getattr(response, "content", []) or []:
        kind = _block_type(block)
        if kind == "text":
            content_parts.append(str(_block_get(block, "text", "")))
        elif kind == "tool_use":
            raw_input = _block_get(block, "input", {}) or {}
            args = raw_input if isinstance(raw_input, dict) else {"value": raw_input}
            tool_calls.append(
                ToolCall(
                    id=str(_block_get(block, "id", "")),
                    name=str(_block_get(block, "name", "")),
                    arguments=cast(dict[str, Any], args),
                )
            )
    usage_obj = getattr(response, "usage", None)
    usage = {
        "input_tokens": int(_block_get(usage_obj, "input_tokens", 0)),
        "output_tokens": int(_block_get(usage_obj, "output_tokens", 0)),
    }
    raw_stop = str(getattr(response, "stop_reason", "") or "")
    stop_reason = "tool_use" if tool_calls or raw_stop == "tool_use" else "end_turn"
    if raw_stop == "max_tokens":
        stop_reason = "max_tokens"
    return CompletionResponse(
        message=Message(role=Role.ASSISTANT, content="".join(content_parts), tool_calls=tool_calls),
        stop_reason=cast(Any, stop_reason),
        usage=usage,
    )


@register("anthropic")
class AnthropicProvider(Provider):
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        super().__init__(model=model, api_key=api_key, base_url=base_url)
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self._token_cache: dict[tuple[str, tuple[int, ...]], int] = {}

    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        messages_api = cast(Any, self.client.messages)
        response = messages_api.create(
            model=self.model,
            system=system,
            messages=anthropic_messages(messages),
            tools=anthropic_tools(tools),
            max_tokens=max_tokens,
        )
        return parse_anthropic_response(response)

    def count_tokens(self, system: str, messages: list[Message]) -> int:
        key = (system, tuple(id(message) for message in messages))
        cached = self._token_cache.get(key)
        if cached is not None:
            return cached
        messages_api = cast(Any, self.client.messages)
        response = messages_api.count_tokens(
            model=self.model,
            system=system,
            messages=anthropic_messages(messages),
        )
        count = int(_block_get(response, "input_tokens", 0))
        self._token_cache[key] = count
        return count

    @property
    def context_window(self) -> int:
        if self.model in _KNOWN_CONTEXT_WINDOWS:
            return _KNOWN_CONTEXT_WINDOWS[self.model]
        logger.warning("unknown Anthropic context window for %s; using 200000", self.model)
        return 200_000
