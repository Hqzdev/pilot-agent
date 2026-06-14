from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pilot_agent.agent.safety import sanitize_jsonable, sanitize_text

_JSON_SCHEMA_KEYS = {
    "type",
    "description",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "default",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
    "anyOf",
    "oneOf",
    "allOf",
}
_JSON_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


@dataclass(frozen=True)
class ToolArgumentParse:
    arguments: dict[str, Any]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def sanitize_tool_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    clean = _sanitize_schema_node(sanitize_jsonable(dict(schema)))
    if clean.get("type") != "object":
        clean["type"] = "object"
    properties = clean.get("properties")
    if not isinstance(properties, dict):
        clean["properties"] = {}
    required = clean.get("required")
    if isinstance(required, list):
        known = set(clean["properties"])
        clean["required"] = [str(item) for item in required if str(item) in known]
    else:
        clean.pop("required", None)
    clean.setdefault("additionalProperties", False)
    return clean


def parse_tool_arguments(raw_arguments: Any, *, tool_name: str) -> ToolArgumentParse:
    raw_text = _strip_code_fence(sanitize_text(str(raw_arguments or "{}")))
    for candidate in _argument_candidates(raw_text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return ToolArgumentParse(arguments=parsed)
        return ToolArgumentParse(
            arguments={"_raw_arguments": raw_text},
            error=f"tool arguments for {tool_name} must decode to an object",
        )
    try:
        json.loads(raw_text)
    except json.JSONDecodeError as exc:
        detail = str(exc)
    else:
        detail = "tool arguments JSON must decode to an object"
    return ToolArgumentParse(
        arguments={"_raw_arguments": raw_text},
        error=f"invalid JSON arguments for {tool_name}: {detail}",
    )


def _sanitize_schema_node(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": "object", "properties": {}, "additionalProperties": False}
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key not in _JSON_SCHEMA_KEYS:
            continue
        if key == "type":
            typed = _sanitize_type(item)
            if typed is not None:
                clean[key] = typed
            continue
        if key == "properties":
            clean[key] = _sanitize_properties(item)
            continue
        if key == "items":
            clean[key] = _sanitize_schema_node(item)
            continue
        if key in {"anyOf", "oneOf", "allOf"}:
            clean[key] = [
                _sanitize_schema_node(entry) for entry in item if isinstance(entry, dict)
            ] if isinstance(item, list) else []
            continue
        if key == "additionalProperties" and isinstance(item, dict):
            clean[key] = _sanitize_schema_node(item)
            continue
        clean[key] = sanitize_jsonable(item)
    return clean


def _sanitize_properties(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(name): _sanitize_schema_node(item)
        for name, item in value.items()
        if isinstance(item, dict)
    }


def _sanitize_type(value: Any) -> str | list[str] | None:
    if isinstance(value, str):
        return value if value in _JSON_TYPES else None
    if isinstance(value, list):
        typed = [str(item) for item in value if str(item) in _JSON_TYPES]
        return typed or None
    return None


def _argument_candidates(raw_text: str) -> list[str]:
    candidates = [raw_text]
    without_trailing_commas = re.sub(r",\s*([}\]])", r"\1", raw_text)
    if without_trailing_commas not in candidates:
        candidates.append(without_trailing_commas)
    single_quoted = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', without_trailing_commas)
    if single_quoted not in candidates:
        candidates.append(single_quoted)
    return candidates


def _strip_code_fence(value: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.S | re.I)
    return match.group(1).strip() if match else value
