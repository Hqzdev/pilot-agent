from __future__ import annotations

import concurrent.futures
import json
import logging
import math
import re
import threading
import time
import traceback
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from pilot_agent.agent.hooks import RuntimeHooks
from pilot_agent.agent.safety import redact_sensitive_text, sanitize_jsonable
from pilot_agent.agent.tool_guardrails import (
    ToolCallGuardrailController,
    append_guardrail_guidance,
)
from pilot_agent.agent.types import ToolCall, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

TOOL_SEARCH_NAME = "tool_search"
TOOL_DESCRIBE_NAME = "tool_describe"
TOOL_CALL_NAME = "tool_call"
BRIDGE_TOOL_NAMES = frozenset({TOOL_SEARCH_NAME, TOOL_DESCRIBE_NAME, TOOL_CALL_NAME})
CHARS_PER_TOKEN = 4.0


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    timeout_s: int = 120
    toolset: str = "core"
    deferrable: bool = False
    parallel_safe: bool = False
    path_scope_args: tuple[str, ...] = ()

    @abstractmethod
    def execute(self, **kwargs: Any) -> str: ...

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    def available(self) -> bool:
        return True


@dataclass(frozen=True)
class ToolSearchSettings:
    enabled: str = "auto"
    threshold_pct: float = 10.0
    search_default_limit: int = 5
    max_search_limit: int = 20

    @classmethod
    def from_raw(cls, raw: object) -> ToolSearchSettings:
        enabled = str(getattr(raw, "enabled", "auto")).lower()
        if enabled not in {"auto", "on", "off"}:
            enabled = "auto"
        return cls(
            enabled=enabled,
            threshold_pct=float(getattr(raw, "threshold_pct", 10.0)),
            search_default_limit=int(getattr(raw, "search_default_limit", 5)),
            max_search_limit=int(getattr(raw, "max_search_limit", 20)),
        )


@dataclass(frozen=True)
class ToolEntry:
    tool: Tool
    check_fn: Callable[[], bool]

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def deferrable(self) -> bool:
        return self.tool.deferrable

    @property
    def parallel_safe(self) -> bool:
        return self.tool.parallel_safe

    @property
    def path_scope_args(self) -> tuple[str, ...]:
        return self.tool.path_scope_args

    def spec(self) -> ToolSpec:
        return self.tool.spec()


@dataclass(frozen=True)
class ToolExecution:
    call: ToolCall
    result: ToolResult
    elapsed_s: float


class ToolRegistry:
    MAX_RESULT_CHARS = 8_000
    CHECK_TTL_S = 30.0
    MAX_SPEC_CACHE = 8

    def __init__(
        self,
        tools: list[Tool],
        project_root: Path,
        guardrails: ToolCallGuardrailController | None = None,
        hooks: RuntimeHooks | None = None,
        tool_search: ToolSearchSettings | None = None,
    ):
        self.tools: dict[str, Tool] = {}
        self.entries: dict[str, ToolEntry] = {}
        self.project_root = project_root.resolve()
        self.artifacts_dir = self.project_root / ".pilot-agent" / "artifacts"
        self.guardrails = guardrails or ToolCallGuardrailController()
        self.hooks = hooks or RuntimeHooks()
        self.tool_search = tool_search or ToolSearchSettings()
        self._generation = 0
        self._check_cache: dict[str, tuple[float, bool]] = {}
        self._spec_cache: dict[tuple[tuple[str, ...] | None, int, int], list[ToolSpec]] = {}
        self._guardrail_lock = threading.Lock()
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool, check_fn: Callable[[], bool] | None = None) -> None:
        if tool.name in BRIDGE_TOOL_NAMES:
            raise ValueError(f"tool name is reserved for the tool-search bridge: {tool.name}")
        self.tools[tool.name] = tool
        self.entries[tool.name] = ToolEntry(tool=tool, check_fn=check_fn or tool.available)
        self._check_cache.pop(tool.name, None)
        self._generation += 1
        self._spec_cache.clear()

    def specs(self, allowed: list[str] | None = None, *, context_window: int = 0) -> list[ToolSpec]:
        names_key = tuple(allowed) if allowed is not None else None
        key = (names_key, self._generation, int(context_window))
        cached = self._spec_cache.get(key)
        if cached is not None:
            return list(cached)

        names = allowed or list(self.tools)
        specs = [
            self.entries[name].spec()
            for name in names
            if name in self.entries and self._entry_available(self.entries[name])
        ]
        specs = self._assemble_tool_search_specs(specs, context_window=context_window)
        if len(self._spec_cache) >= self.MAX_SPEC_CACHE:
            self._spec_cache.pop(next(iter(self._spec_cache)))
        self._spec_cache[key] = specs
        return list(specs)

    def execute(self, call: ToolCall, context: Mapping[str, Any] | None = None) -> ToolResult:
        context_data = dict(context or {})
        if call.name in BRIDGE_TOOL_NAMES:
            return self._execute_bridge(call, context_data)
        tool = self.tools.get(call.name)
        if tool is None:
            return self._result(call.id, f"unknown tool: {call.name}", is_error=True)

        request_mw = self.hooks.apply_tool_request_middleware(
            call.name,
            dict(call.arguments),
            **context_data,
            tool_call_id=call.id,
        )
        arguments = sanitize_jsonable(request_mw.payload)
        if not isinstance(arguments, dict):
            arguments = {}
        block_message = self.hooks.get_tool_block_message(
            call.name,
            arguments,
            **context_data,
            tool_call_id=call.id,
            middleware_trace=request_mw.trace,
        )
        if block_message is not None:
            result = self._result(call.id, block_message, is_error=True)
            self._emit_post_tool(call, arguments, result, status="blocked", context=context_data)
            return result

        with self._guardrail_lock:
            decision = self.guardrails.before_call(call.name, arguments)
        if not decision.allows_execution:
            result = self._result(call.id, decision.message, is_error=True)
            self._emit_post_tool(call, arguments, result, status="blocked", context=context_data)
            return result

        try:
            validate(instance=arguments, schema=tool.parameters)
        except ValidationError as exc:
            result = self._result(
                call.id,
                f"argument validation failed: {exc.message}",
                is_error=True,
            )
            self._record_guardrail_after(call.name, arguments, result, failed=True)
            self._emit_post_tool(call, arguments, result, status="error", context=context_data)
            return result

        executor: concurrent.futures.ThreadPoolExecutor | None = None
        started_at = time.monotonic()
        try:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                self.hooks.run_tool_execution_middleware,
                call.name,
                arguments,
                lambda next_args: tool.execute(**next_args),
                **context_data,
                tool_call_id=call.id,
            )
            output = future.result(timeout=tool.timeout_s)
            executor.shutdown(wait=True)
            observed = self._result(call.id, str(output), is_error=False)
            self._emit_post_tool(
                call,
                arguments,
                observed,
                status="ok",
                context=context_data,
                duration_ms=int((time.monotonic() - started_at) * 1000),
            )
            transformed = self.hooks.transform_tool_result(
                observed.content,
                tool_name=call.name,
                args=arguments,
                **context_data,
                tool_call_id=call.id,
            )
            result = observed if transformed == observed.content else self._result(
                call.id,
                transformed,
                is_error=False,
            )
        except concurrent.futures.TimeoutError:
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            result = self._result(call.id, f"tool timed out after {tool.timeout_s}s", is_error=True)
            self._emit_post_tool(call, arguments, result, status="error", context=context_data)
        except Exception:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
            result = self._result(call.id, traceback.format_exc(limit=5), is_error=True)
            self._emit_post_tool(call, arguments, result, status="error", context=context_data)

        self._record_guardrail_after(call.name, arguments, result, failed=result.is_error)
        return result

    def execute_batch(
        self,
        calls: list[ToolCall],
        context: Mapping[str, Any] | None = None,
    ) -> list[ToolExecution]:
        if not self._should_parallelize(calls):
            return [self._execute_timed(call, context=context) for call in calls]
        max_workers = min(4, len(calls))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._execute_timed, call, context=context) for call in calls
            ]
            return [future.result() for future in futures]

    def _execute_timed(
        self,
        call: ToolCall,
        context: Mapping[str, Any] | None = None,
    ) -> ToolExecution:
        started_at = time.monotonic()
        result = self.execute(call, context=context)
        return ToolExecution(call=call, result=result, elapsed_s=time.monotonic() - started_at)

    def _record_guardrail_after(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        *,
        failed: bool,
    ) -> None:
        with self._guardrail_lock:
            after = self.guardrails.after_call(
                tool_name,
                arguments,
                result.content,
                failed=failed,
            )
        if after.action == "warn":
            result.content = append_guardrail_guidance(result.content, after)

    def _entry_available(self, entry: ToolEntry) -> bool:
        cached = self._check_cache.get(entry.name)
        now = time.monotonic()
        if cached is not None:
            created_at, value = cached
            if now - created_at < self.CHECK_TTL_S:
                return value
        try:
            value = bool(entry.check_fn())
        except Exception as exc:
            logger.debug("tool availability check failed for %s: %s", entry.name, exc)
            value = False
        self._check_cache[entry.name] = (now, value)
        return value

    def _artifact_path(self, call_id: str) -> Path:
        safe_id = call_id.replace("/", "_").replace(":", "_")
        return self.artifacts_dir / f"{safe_id}.txt"

    def _result(self, call_id: str, output: str, *, is_error: bool) -> ToolResult:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        output = redact_sensitive_text(output)
        artifact = self._artifact_path(call_id)
        artifact.write_text(output, encoding="utf-8")
        if len(output) <= self.MAX_RESULT_CHARS:
            return ToolResult(
                tool_call_id=call_id,
                content=output,
                is_error=is_error,
                artifact_path=str(artifact),
            )
        head = output[:4_000]
        tail = output[-4_000:]
        content = f"{head}\n...[truncated, full output: {artifact}]...\n{tail}"
        return ToolResult(
            tool_call_id=call_id,
            content=content,
            is_error=is_error,
            truncated=True,
            artifact_path=str(artifact),
        )

    def _emit_post_tool(
        self,
        call: ToolCall,
        args: dict[str, Any],
        result: ToolResult,
        *,
        status: str,
        context: dict[str, Any],
        duration_ms: int = 0,
    ) -> None:
        self.hooks.invoke_hook(
            "post_tool_call",
            tool_name=call.name,
            args=args,
            result=result.content,
            status=status,
            is_error=result.is_error,
            tool_call_id=call.id,
            duration_ms=duration_ms,
            artifact_path=result.artifact_path or "",
            **context,
        )

    def _assemble_tool_search_specs(
        self,
        specs: list[ToolSpec],
        *,
        context_window: int,
    ) -> list[ToolSpec]:
        if self.tool_search.enabled == "off":
            return specs
        deferred = [
            spec
            for spec in specs
            if spec.name in self.entries and self.entries[spec.name].deferrable
        ]
        if not deferred:
            return specs
        deferred_tokens = _estimate_spec_tokens(deferred)
        if self.tool_search.enabled == "auto":
            threshold = int(context_window * (self.tool_search.threshold_pct / 100.0))
            if context_window > 0 and deferred_tokens < threshold:
                return specs
            if context_window <= 0 and deferred_tokens < 20_000:
                return specs
        deferred_names = {item.name for item in deferred}
        visible = [spec for spec in specs if spec.name not in deferred_names]
        return [*visible, *_bridge_specs(len(deferred))]

    def _execute_bridge(self, call: ToolCall, context: dict[str, Any]) -> ToolResult:
        allowed = context.get("allowed_tools")
        allowed_names = [str(item) for item in allowed] if isinstance(allowed, list) else None
        deferred = self._deferred_specs(allowed_names)
        if call.name == TOOL_SEARCH_NAME:
            query = str(call.arguments.get("query") or "").strip()
            if not query:
                return self._result(call.id, "query is required", is_error=True)
            limit = _safe_int(call.arguments.get("limit"), self.tool_search.search_default_limit)
            limit = max(1, min(self.tool_search.max_search_limit, limit))
            matches = _search_specs(deferred, query, limit)
            payload = {
                "matches": [
                    {"name": spec.name, "description": spec.description[:400]} for spec in matches
                ]
            }
            return self._result(call.id, json.dumps(payload, ensure_ascii=False), is_error=False)
        if call.name == TOOL_DESCRIBE_NAME:
            name = str(call.arguments.get("name") or "")
            spec = next((item for item in deferred if item.name == name), None)
            if spec is None:
                return self._result(call.id, f"unknown deferred tool: {name}", is_error=True)
            return self._result(
                call.id,
                json.dumps(spec.__dict__, ensure_ascii=False),
                is_error=False,
            )
        if call.name == TOOL_CALL_NAME:
            name = str(call.arguments.get("name") or "")
            arguments = call.arguments.get("arguments")
            if not isinstance(arguments, dict):
                return self._result(call.id, "tool_call.arguments must be an object", is_error=True)
            if name not in {spec.name for spec in deferred}:
                return self._result(
                    call.id,
                    f"deferred tool unavailable in this scope: {name}",
                    is_error=True,
                )
            return self.execute(
                ToolCall(id=call.id, name=name, arguments=arguments),
                context={**context, "bridge_tool": TOOL_CALL_NAME},
            )
        return self._result(call.id, f"unknown bridge tool: {call.name}", is_error=True)

    def _deferred_specs(self, allowed: list[str] | None) -> list[ToolSpec]:
        names = allowed or list(self.tools)
        return [
            self.entries[name].spec()
            for name in names
            if name in self.entries
            and self.entries[name].deferrable
            and self._entry_available(self.entries[name])
        ]

    def _should_parallelize(self, calls: list[ToolCall]) -> bool:
        if len(calls) <= 1:
            return False
        entries: list[ToolEntry] = []
        for call in calls:
            if call.name in BRIDGE_TOOL_NAMES:
                return False
            entry = self.entries.get(call.name)
            if entry is None:
                return False
            entries.append(entry)
        if all(entry.parallel_safe for entry in entries):
            return True
        reserved_paths: list[Path] = []
        for entry, call in zip(entries, calls, strict=True):
            scoped = self._path_scope(entry, call.arguments)
            if scoped is None:
                return False
            if any(_paths_overlap(scoped, existing) for existing in reserved_paths):
                return False
            reserved_paths.append(scoped)
        return True

    def _path_scope(self, entry: ToolEntry, args: Mapping[str, Any]) -> Path | None:
        for key in entry.path_scope_args:
            value = args.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = self.project_root / candidate
            return candidate.absolute()
        return None


def _estimate_spec_tokens(specs: Iterable[ToolSpec]) -> int:
    chars = 0
    for spec in specs:
        try:
            chars += len(json.dumps(spec.__dict__, ensure_ascii=False, default=str))
        except TypeError:
            chars += len(str(spec))
    return int(math.ceil(chars / CHARS_PER_TOKEN))


def _bridge_specs(count: int) -> list[ToolSpec]:
    return [
        ToolSpec(
            name=TOOL_SEARCH_NAME,
            description=(
                f"Search {count} additional tools loaded on demand. Follow with "
                f"{TOOL_DESCRIBE_NAME}, then {TOOL_CALL_NAME}."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name=TOOL_DESCRIBE_NAME,
            description="Load the full JSON schema for one deferred tool.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name=TOOL_CALL_NAME,
            description="Invoke a deferred tool by exact name and arguments.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["name", "arguments"],
                "additionalProperties": False,
            },
        ),
    ]


def _search_specs(specs: list[ToolSpec], query: str, limit: int) -> list[ToolSpec]:
    tokens = _tokenize(query)
    if not tokens:
        return []
    scored: list[tuple[int, ToolSpec]] = []
    for spec in specs:
        text = f"{spec.name} {spec.name.replace('_', ' ')} {spec.description}"
        text_tokens = set(_tokenize(text))
        score = sum(1 for token in tokens if token in text_tokens)
        if score:
            scored.append((score, spec))
    if not scored:
        lowered = query.lower()
        scored = [(1, spec) for spec in specs if lowered in spec.name.lower()]
    scored.sort(key=lambda item: (-item[0], item[1].name))
    return [spec for _, spec in scored[:limit]]


def _tokenize(value: str) -> list[str]:
    return [part.lower() for part in re.findall(r"[A-Za-z0-9]+", value)]


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _paths_overlap(left: Path, right: Path) -> bool:
    left_parts = left.parts
    right_parts = right.parts
    common = min(len(left_parts), len(right_parts))
    return left_parts[:common] == right_parts[:common]
