from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Literal, cast


class Role(str, Enum):  # noqa: UP042 - canonical spec requires `str, Enum`.
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False
    truncated: bool = False
    artifact_path: str | None = None


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    tokens: int | None = None
    pinned: bool = False
    phase: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class CompletionResponse:
    message: Message
    stop_reason: Literal["end_turn", "tool_use", "max_tokens"]
    usage: dict[str, int]


@dataclass
class SessionEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


Jsonable = ToolCall | ToolResult | Message | ToolSpec | CompletionResponse | SessionEvent
_TYPE_MAP = {
    "ToolCall": ToolCall,
    "ToolResult": ToolResult,
    "Message": Message,
    "ToolSpec": ToolSpec,
    "CompletionResponse": CompletionResponse,
    "SessionEvent": SessionEvent,
}


def _with_type(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        data = asdict(obj)
        data["_type"] = obj.__class__.__name__
        return data
    raise TypeError(f"cannot serialize object of type {type(obj).__name__}")


def to_json(obj: Jsonable) -> str:
    """Serialize a canonical dataclass with a `_type` marker."""

    return json.dumps(_with_type(obj), ensure_ascii=False)


def _ensure_type(data: dict[str, Any]) -> type[Any]:
    type_name = data.get("_type")
    if not isinstance(type_name, str) or type_name not in _TYPE_MAP:
        raise ValueError("serialized object is missing a valid _type field")
    return _TYPE_MAP[type_name]


def _decode_tool_call(data: dict[str, Any]) -> ToolCall:
    return ToolCall(
        id=str(data["id"]),
        name=str(data["name"]),
        arguments=cast(dict[str, Any], data.get("arguments") or {}),
    )


def _decode_tool_result(data: dict[str, Any]) -> ToolResult:
    return ToolResult(
        tool_call_id=str(data["tool_call_id"]),
        content=str(data.get("content", "")),
        is_error=bool(data.get("is_error", False)),
        truncated=bool(data.get("truncated", False)),
        artifact_path=cast(str | None, data.get("artifact_path")),
    )


def _decode_message(data: dict[str, Any]) -> Message:
    role = data.get("role")
    return Message(
        role=role if isinstance(role, Role) else Role(str(role)),
        content=str(data.get("content", "")),
        tool_calls=[_decode_tool_call(item) for item in data.get("tool_calls", [])],
        tool_results=[_decode_tool_result(item) for item in data.get("tool_results", [])],
        tokens=cast(int | None, data.get("tokens")),
        pinned=bool(data.get("pinned", False)),
        phase=cast(str | None, data.get("phase")),
    )


def _decode_tool_spec(data: dict[str, Any]) -> ToolSpec:
    return ToolSpec(
        name=str(data["name"]),
        description=str(data["description"]),
        parameters=cast(dict[str, Any], data.get("parameters") or {}),
    )


def _decode_completion(data: dict[str, Any]) -> CompletionResponse:
    message_data = cast(dict[str, Any], data["message"])
    if message_data.get("_type") == "Message":
        message = cast(Message, from_json(json.dumps(message_data)))
    else:
        message = _decode_message(message_data)
    stop_reason = cast(Literal["end_turn", "tool_use", "max_tokens"], data["stop_reason"])
    return CompletionResponse(
        message=message,
        stop_reason=stop_reason,
        usage=cast(dict[str, int], data.get("usage") or {}),
    )


def _decode_session_event(data: dict[str, Any]) -> SessionEvent:
    return SessionEvent(
        event_type=str(data["event_type"]),
        payload=cast(dict[str, Any], data.get("payload") or {}),
    )


def from_json(raw: str) -> Jsonable:
    """Deserialize a canonical dataclass serialized by `to_json`."""

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("serialized object must be a JSON object")
    cls = _ensure_type(data)
    clean = dict(data)
    clean.pop("_type", None)
    if cls is ToolCall:
        return _decode_tool_call(clean)
    if cls is ToolResult:
        return _decode_tool_result(clean)
    if cls is Message:
        return _decode_message(clean)
    if cls is ToolSpec:
        return _decode_tool_spec(clean)
    if cls is CompletionResponse:
        return _decode_completion(clean)
    if cls is SessionEvent:
        return _decode_session_event(clean)
    raise AssertionError(f"unsupported serialized type: {cls.__name__}")
