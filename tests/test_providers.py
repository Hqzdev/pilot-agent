from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from devagent.agent.types import Message, Role, ToolCall, ToolResult, ToolSpec
from devagent.providers.anthropic import (
    AnthropicProvider,
    anthropic_messages,
    anthropic_tools,
    parse_anthropic_response,
)
from devagent.providers.base import Provider, from_config, register
from devagent.providers.openai import (
    OpenAIProvider,
    openai_messages,
    openai_tools,
    parse_openai_response,
)
from devagent.providers.openrouter import _MODEL_CACHE, OpenRouterProvider


def test_anthropic_tool_spec_uses_input_schema() -> None:
    tools = [ToolSpec("read_file", "Read a file", {"type": "object", "properties": {}})]

    assert anthropic_tools(tools) == [
        {
            "name": "read_file",
            "description": "Read a file",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


def test_anthropic_assistant_tool_call_conversion() -> None:
    msg = Message(
        role=Role.ASSISTANT,
        content="Need context.",
        tool_calls=[ToolCall(id="abc", name="read_file", arguments={"path": "pyproject.toml"})],
    )

    converted = anthropic_messages([msg])

    assert converted == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Need context."},
                {
                    "type": "tool_use",
                    "id": "abc",
                    "name": "read_file",
                    "input": {"path": "pyproject.toml"},
                },
            ],
        }
    ]


def test_anthropic_consecutive_tool_results_merge_into_user_message() -> None:
    messages = [
        Message(role=Role.TOOL, tool_results=[ToolResult("a", "first")]),
        Message(role=Role.TOOL, tool_results=[ToolResult("b", "second", is_error=True)]),
    ]

    converted = anthropic_messages(messages)

    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "first"},
                {
                    "type": "tool_result",
                    "tool_use_id": "b",
                    "content": "second",
                    "is_error": True,
                },
            ],
        }
    ]


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] | None = None


@dataclass
class Response:
    content: list[Block]
    stop_reason: str
    usage: Usage


def test_parse_anthropic_response_to_canonical_message() -> None:
    response = Response(
        content=[
            Block(type="text", text="I will do it."),
            Block(type="tool_use", id="toolu_1", name="bash", input={"command": "pwd"}),
        ],
        stop_reason="tool_use",
        usage=Usage(input_tokens=10, output_tokens=5),
    )

    parsed = parse_anthropic_response(response)

    assert parsed.stop_reason == "tool_use"
    assert parsed.usage == {"input_tokens": 10, "output_tokens": 5}
    assert parsed.message.content == "I will do it."
    assert parsed.message.tool_calls == [ToolCall("toolu_1", "bash", {"command": "pwd"})]


def test_openai_tool_spec_and_message_conversion() -> None:
    messages = [
        Message(role=Role.USER, content="run it"),
        Message(
            role=Role.ASSISTANT,
            content="calling",
            tool_calls=[ToolCall(id="call_1", name="bash", arguments={"command": "pwd"})],
        ),
        Message(role=Role.TOOL, tool_results=[ToolResult(tool_call_id="call_1", content="/tmp")]),
    ]

    converted = openai_messages(messages)

    assert openai_tools([ToolSpec("bash", "Run shell", {"type": "object"})]) == [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run shell",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert converted[1]["tool_calls"][0]["function"]["arguments"] == '{"command": "pwd"}'
    assert converted[2] == {"role": "tool", "tool_call_id": "call_1", "content": "/tmp"}


def test_openai_response_parses_to_canonical_message() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": "Need a tool",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }

    parsed = parse_openai_response(response)

    assert parsed.stop_reason == "tool_use"
    assert parsed.message.role is Role.ASSISTANT
    assert parsed.message.content == "Need a tool"
    assert parsed.message.tool_calls == [ToolCall("call_1", "read_file", {"path": "README.md"})]
    assert parsed.usage == {"input_tokens": 11, "output_tokens": 7}


def test_openai_broken_json_returns_tool_result_error() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_bad",
                            "function": {"name": "bash", "arguments": '{"command": '},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }

    parsed = parse_openai_response(response)

    assert parsed.stop_reason == "tool_use"
    assert parsed.message.role is Role.TOOL
    assert parsed.message.tool_results == [
        ToolResult(
            tool_call_id="call_bad",
            content=(
                "invalid JSON arguments for bash: "
                "Expecting value: line 1 column 13 (char 12)"
            ),
            is_error=True,
        )
    ]


def test_anthropic_complete_uses_mocked_client(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = AnthropicProvider(model="claude-sonnet-4-6", api_key="test")
    response = Response(
        content=[Block(type="tool_use", id="x", name="read_file", input={"path": "README.md"})],
        stop_reason="tool_use",
        usage=Usage(input_tokens=1, output_tokens=2),
    )

    class Messages:
        def create(self, **kwargs: Any) -> Response:
            assert kwargs["model"] == "claude-sonnet-4-6"
            assert kwargs["system"] == "sys"
            return response

        def count_tokens(self, **kwargs: Any) -> Any:
            return type("TokenCount", (), {"input_tokens": 123})()

    provider.client = type("Client", (), {"messages": Messages()})()

    completion = provider.complete("sys", [], [], max_tokens=100)

    assert completion.message.tool_calls[0].name == "read_file"
    assert provider.count_tokens("sys", []) == 123
    assert provider.count_tokens("sys", []) == 123


def test_openai_complete_uses_mocked_client_and_counts_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAIProvider(model="unknown-model", api_key="test")

    class FakeEncoding:
        def encode(self, text: str) -> list[int]:
            return list(range(len(text.split()) or 1))

    def unknown_model(model: str) -> FakeEncoding:
        raise KeyError(model)

    monkeypatch.setattr("devagent.providers.openai.tiktoken.encoding_for_model", unknown_model)
    monkeypatch.setattr(
        "devagent.providers.openai.tiktoken.get_encoding",
        lambda name: FakeEncoding(),
    )

    class Completions:
        def create(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["messages"][0] == {"role": "system", "content": "sys"}
            assert kwargs["tools"][0]["function"]["name"] == "bash"
            return {
                "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            }

    provider.client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": Completions()})()},
    )()

    completion = provider.complete(
        "sys",
        [Message(role=Role.USER, content="hello")],
        [ToolSpec("bash", "Run shell", {"type": "object"})],
    )

    assert completion.stop_reason == "end_turn"
    assert completion.message.content == "done"
    assert provider.count_tokens("sys", [Message(role=Role.USER, content="hello")]) > 0
    assert provider.context_window == 128_000


def test_openrouter_context_window_fetch_cache_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _MODEL_CACHE.clear()
    provider = OpenRouterProvider(model="openai/test", api_key="test")

    class ResponseOk:
        def json(self) -> dict[str, Any]:
            return {"data": [{"id": "openai/test", "context_length": 99_999}]}

    calls = 0

    def fake_get(url: str, timeout: int) -> ResponseOk:
        nonlocal calls
        calls += 1
        assert url.endswith("/models")
        assert timeout == 5
        return ResponseOk()

    monkeypatch.setattr("devagent.providers.openrouter.requests.get", fake_get)

    assert provider.context_window == 99_999
    assert provider.context_window == 99_999
    assert calls == 1

    _MODEL_CACHE.clear()

    def failing_get(url: str, timeout: int) -> ResponseOk:
        raise RuntimeError("offline")

    monkeypatch.setattr("devagent.providers.openrouter.requests.get", failing_get)
    assert OpenRouterProvider(model="missing/model", api_key="test").context_window == 128_000


class RetryableError(Exception):
    status_code = 429


class NonRetryableError(Exception):
    status_code = 400


@register("retry-test")
class RetryProvider(Provider):
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        super().__init__(model, api_key, base_url)
        self.calls = 0

    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ):
        self.calls += 1
        if self.calls < 2:
            raise RetryableError("rate limited")
        return type(
            "Completion",
            (),
            {"message": Message(Role.ASSISTANT), "stop_reason": "end_turn", "usage": {}},
        )()

    def count_tokens(self, system: str, messages: list[Message]) -> int:
        return 0

    @property
    def context_window(self) -> int:
        return 10


@register("no-retry-test")
class NoRetryProvider(RetryProvider):
    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ):
        self.calls += 1
        raise NonRetryableError("bad request")


def test_provider_factory_uses_registry_without_if_else() -> None:
    class Cfg:
        provider = "retry-test"
        model = "m"
        base_url = None

        def resolve_key(self) -> str:
            return "key"

    assert isinstance(from_config(Cfg()), RetryProvider)


def test_provider_base_retries_429_and_not_400() -> None:
    retrying = RetryProvider("m", "k")
    retrying.complete("", [], [])
    assert retrying.calls == 2

    no_retry = NoRetryProvider("m", "k")
    with pytest.raises(NonRetryableError):
        no_retry.complete("", [], [])
    assert no_retry.calls == 1
