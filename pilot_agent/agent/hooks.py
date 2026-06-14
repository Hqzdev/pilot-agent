from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

OBSERVER_SCHEMA_VERSION = "pilot.observer.v1"
MIDDLEWARE_SCHEMA_VERSION = "pilot.middleware.v1"

VALID_HOOKS = frozenset(
    {
        "pre_tool_call",
        "post_tool_call",
        "transform_tool_result",
        "pre_llm_call",
        "post_llm_call",
        "api_request_error",
        "on_compaction",
        "on_session_event",
    }
)

TOOL_REQUEST_MIDDLEWARE = "tool_request"
TOOL_EXECUTION_MIDDLEWARE = "tool_execution"
LLM_REQUEST_MIDDLEWARE = "llm_request"
LLM_EXECUTION_MIDDLEWARE = "llm_execution"
VALID_MIDDLEWARE = frozenset(
    {
        TOOL_REQUEST_MIDDLEWARE,
        TOOL_EXECUTION_MIDDLEWARE,
        LLM_REQUEST_MIDDLEWARE,
        LLM_EXECUTION_MIDDLEWARE,
    }
)

HookCallback = Callable[..., Any]
ExecutionCallback = Callable[[Any], Any]


@dataclass
class RequestMiddlewareResult:
    payload: Any
    original_payload: Any
    changed: bool = False
    trace: list[dict[str, Any]] = field(default_factory=list)


def observer_payload(**kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("telemetry_schema_version", OBSERVER_SCHEMA_VERSION)
    return kwargs


def middleware_payload(**kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("telemetry_schema_version", OBSERVER_SCHEMA_VERSION)
    kwargs.setdefault("middleware_schema_version", MIDDLEWARE_SCHEMA_VERSION)
    return kwargs


def _safe_copy(payload: Any) -> Any:
    try:
        return deepcopy(payload)
    except Exception as exc:
        logger.debug("deepcopy failed for middleware payload: %s", exc)
        return dict(payload) if isinstance(payload, dict) else payload


def _trace_entry(result: dict[str, Any]) -> dict[str, Any]:
    name = result.get("name") or result.get("middleware") or result.get("id") or "anonymous"
    entry: dict[str, Any] = {"name": str(name)}
    if result.get("changed") is not None:
        entry["changed"] = bool(result.get("changed"))
    if result.get("reason"):
        entry["reason"] = str(result["reason"])
    return entry


class RuntimeHooks:
    """In-process hook and middleware registry for the agent harness.

    This intentionally does not discover or import arbitrary plugins. It gives
    the core loop a stable extension contract that tests and future first-party
    integrations can use without adding conditionals to AgentLoop.
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookCallback]] = {name: [] for name in VALID_HOOKS}
        self._middleware: dict[str, list[HookCallback]] = {
            name: [] for name in VALID_MIDDLEWARE
        }

    def register_hook(self, name: str, callback: HookCallback) -> None:
        if name not in VALID_HOOKS:
            raise ValueError(f"unknown hook: {name}")
        self._hooks[name].append(callback)

    def register_middleware(self, kind: str, callback: HookCallback) -> None:
        if kind not in VALID_MIDDLEWARE:
            raise ValueError(f"unknown middleware: {kind}")
        self._middleware[kind].append(callback)

    def has_hook(self, name: str) -> bool:
        return bool(self._hooks.get(name))

    def has_middleware(self, kind: str) -> bool:
        return bool(self._middleware.get(kind))

    def invoke_hook(self, name: str, **kwargs: Any) -> list[Any]:
        callbacks = self._hooks.get(name, [])
        if not callbacks:
            return []
        payload = observer_payload(**kwargs)
        results: list[Any] = []
        for callback in list(callbacks):
            try:
                results.append(callback(**payload))
            except Exception as exc:
                logger.debug("hook %s failed: %s", name, exc)
        return results

    def get_tool_block_message(
        self,
        tool_name: str,
        args: dict[str, Any],
        **context: Any,
    ) -> str | None:
        for result in self.invoke_hook("pre_tool_call", tool_name=tool_name, args=args, **context):
            if isinstance(result, str) and result:
                return result
            if not isinstance(result, dict):
                continue
            action = str(result.get("action") or result.get("decision") or "").lower()
            if action in {"block", "deny"}:
                message = result.get("message") or result.get("reason") or "blocked by hook"
                return str(message)
        return None

    def transform_tool_result(
        self,
        result: str,
        *,
        tool_name: str,
        args: dict[str, Any],
        **context: Any,
    ) -> str:
        for hook_result in self.invoke_hook(
            "transform_tool_result",
            tool_name=tool_name,
            args=args,
            result=result,
            **context,
        ):
            if isinstance(hook_result, str):
                return hook_result
        return result

    def apply_tool_request_middleware(
        self,
        tool_name: str,
        args: dict[str, Any],
        **context: Any,
    ) -> RequestMiddlewareResult:
        return self._apply_request_middleware(
            TOOL_REQUEST_MIDDLEWARE,
            payload_key="args",
            payload=args,
            tool_name=tool_name,
            **context,
        )

    def apply_llm_request_middleware(
        self,
        request: dict[str, Any],
        **context: Any,
    ) -> RequestMiddlewareResult:
        return self._apply_request_middleware(
            LLM_REQUEST_MIDDLEWARE,
            payload_key="request",
            payload=request,
            **context,
        )

    def run_tool_execution_middleware(
        self,
        tool_name: str,
        args: dict[str, Any],
        next_call: ExecutionCallback,
        **context: Any,
    ) -> Any:
        return self._run_execution_middleware(
            TOOL_EXECUTION_MIDDLEWARE,
            payload=args,
            next_call=next_call,
            tool_name=tool_name,
            **context,
        )

    def run_llm_execution_middleware(
        self,
        request: dict[str, Any],
        next_call: ExecutionCallback,
        **context: Any,
    ) -> Any:
        return self._run_execution_middleware(
            LLM_EXECUTION_MIDDLEWARE,
            payload=request,
            next_call=next_call,
            **context,
        )

    def _apply_request_middleware(
        self,
        kind: str,
        *,
        payload_key: str,
        payload: Any,
        **context: Any,
    ) -> RequestMiddlewareResult:
        callbacks = self._middleware.get(kind, [])
        if not callbacks:
            return RequestMiddlewareResult(payload=payload, original_payload=payload)

        original = _safe_copy(payload)
        current = _safe_copy(original)
        trace: list[dict[str, Any]] = []
        for callback in list(callbacks):
            try:
                result = callback(
                    **middleware_payload(
                        **{payload_key: current, f"original_{payload_key}": original},
                        **context,
                    )
                )
            except Exception as exc:
                logger.debug("request middleware %s failed: %s", kind, exc)
                continue
            if not isinstance(result, dict):
                continue
            next_payload = result.get(payload_key)
            if next_payload is None:
                continue
            current = _safe_copy(next_payload)
            trace.append(_trace_entry(result))
        return RequestMiddlewareResult(
            payload=current,
            original_payload=original,
            changed=bool(trace),
            trace=trace,
        )

    def _run_execution_middleware(
        self,
        kind: str,
        *,
        payload: Any,
        next_call: ExecutionCallback,
        **context: Any,
    ) -> Any:
        callbacks = list(self._middleware.get(kind, []))
        if not callbacks:
            return next_call(payload)

        def call_at(index: int, current_payload: Any) -> Any:
            if index >= len(callbacks):
                return next_call(current_payload)
            callback = callbacks[index]
            next_used = False

            def downstream(next_payload: Any | None = None) -> Any:
                nonlocal next_used
                if next_used:
                    raise RuntimeError("execution middleware called next_call more than once")
                next_used = True
                return call_at(index + 1, current_payload if next_payload is None else next_payload)

            try:
                return callback(
                    **middleware_payload(payload=current_payload, next_call=downstream, **context)
                )
            except Exception as exc:
                logger.debug("execution middleware %s failed: %s", kind, exc)
                return downstream(current_payload)

        return call_at(0, payload)
