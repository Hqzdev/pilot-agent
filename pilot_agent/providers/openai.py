from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Any, cast

import openai
import tiktoken

from pilot_agent.agent.safety import sanitize_jsonable, sanitize_text
from pilot_agent.agent.types import (
    CompletionResponse,
    Message,
    Role,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from pilot_agent.providers.base import Provider, register

logger = logging.getLogger(__name__)

_KNOWN_CONTEXT_WINDOWS = {
    "gpt-5": 400_000,
    "gpt-5-mini": 400_000,
    "gpt-4.1": 1_000_000,
    "gpt-4.1-mini": 1_000_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
}


def openai_tools(tools: Iterable[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message.role is Role.TOOL:
            for result in message.tool_results:
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "content": result.content,
                    }
                )
            continue
        item: dict[str, Any] = {
            "role": message.role.value,
            "content": sanitize_text(message.content),
        }
        if message.role is Role.ASSISTANT and message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(sanitize_jsonable(call.arguments)),
                    },
                }
                for call in message.tool_calls
            ]
        converted.append(item)
    return converted


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def parse_openai_message(raw_message: Any) -> Message:
    content = _get(raw_message, "content", "") or ""
    raw_tool_calls = _get(raw_message, "tool_calls", []) or []
    tool_calls: list[ToolCall] = []
    errors: list[ToolResult] = []
    for raw_call in raw_tool_calls:
        function = _get(raw_call, "function", {}) or {}
        call_id = str(_get(raw_call, "id", ""))
        name = str(_get(function, "name", ""))
        raw_args = _get(function, "arguments", "{}") or "{}"
        try:
            args = json.loads(sanitize_text(str(raw_args)))
            if not isinstance(args, dict):
                raise ValueError("tool arguments JSON must decode to an object")
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(
                ToolResult(
                    tool_call_id=call_id,
                    content=f"invalid JSON arguments for {name}: {exc}",
                    is_error=True,
                )
            )
            args = {"_raw_arguments": str(raw_args)}
        tool_calls.append(ToolCall(id=call_id, name=name, arguments=cast(dict[str, Any], args)))
    if errors:
        return Message(role=Role.TOOL, tool_results=errors)
    return Message(role=Role.ASSISTANT, content=sanitize_text(str(content)), tool_calls=tool_calls)


def parse_openai_response(response: Any) -> CompletionResponse:
    choices = _get(response, "choices", []) or []
    first = choices[0] if choices else {}
    raw_message = _get(first, "message", {}) or {}
    message = parse_openai_message(raw_message)
    finish_reason = str(_get(first, "finish_reason", "") or "")
    if finish_reason == "tool_calls" or message.tool_calls:
        stop_reason = "tool_use"
    elif finish_reason == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"
    usage_obj = _get(response, "usage", {}) or {}
    usage = {
        "input_tokens": int(_get(usage_obj, "prompt_tokens", 0)),
        "output_tokens": int(_get(usage_obj, "completion_tokens", 0)),
    }
    return CompletionResponse(message=message, stop_reason=cast(Any, stop_reason), usage=usage)


@register("openai")
class OpenAIProvider(Provider):
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        super().__init__(model=model, api_key=api_key, base_url=base_url)
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = openai.OpenAI(**kwargs)

    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        all_messages = [{"role": "system", "content": system}, *openai_messages(messages)]
        completions = cast(Any, self.client.chat.completions)
        response = completions.create(
            model=self.model,
            messages=all_messages,
            tools=openai_tools(tools),
            max_tokens=max_tokens,
        )
        return parse_openai_response(response)

    def count_tokens(self, system: str, messages: list[Message]) -> int:
        try:
            encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            encoding = tiktoken.get_encoding("o200k_base")
        total = len(encoding.encode(system)) + 4
        for message in messages:
            total += 4 + len(encoding.encode(message.content))
            for call in message.tool_calls:
                total += len(encoding.encode(call.name))
                total += len(encoding.encode(json.dumps(call.arguments)))
            for result in message.tool_results:
                total += len(encoding.encode(result.content))
        return total

    @property
    def context_window(self) -> int:
        if self.model in _KNOWN_CONTEXT_WINDOWS:
            return _KNOWN_CONTEXT_WINDOWS[self.model]
        logger.warning("unknown OpenAI context window for %s; using 128000", self.model)
        return 128_000
