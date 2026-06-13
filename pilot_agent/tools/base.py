from __future__ import annotations

import concurrent.futures
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from pilot_agent.agent.safety import redact_sensitive_text, sanitize_jsonable
from pilot_agent.agent.tool_guardrails import (
    ToolCallGuardrailController,
    append_guardrail_guidance,
)
from pilot_agent.agent.types import ToolCall, ToolResult, ToolSpec


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    timeout_s: int = 120

    @abstractmethod
    def execute(self, **kwargs: Any) -> str: ...

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)


class ToolRegistry:
    MAX_RESULT_CHARS = 8_000

    def __init__(
        self,
        tools: list[Tool],
        project_root: Path,
        guardrails: ToolCallGuardrailController | None = None,
    ):
        self.tools = {tool.name: tool for tool in tools}
        self.project_root = project_root.resolve()
        self.artifacts_dir = self.project_root / ".pilot-agent" / "artifacts"
        self.guardrails = guardrails or ToolCallGuardrailController()

    def specs(self, allowed: list[str] | None = None) -> list[ToolSpec]:
        names = allowed or list(self.tools)
        return [self.tools[name].spec() for name in names if name in self.tools]

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.name)
        if tool is None:
            return self._result(call.id, f"unknown tool: {call.name}", is_error=True)
        arguments = sanitize_jsonable(call.arguments)
        decision = self.guardrails.before_call(call.name, arguments)
        if not decision.allows_execution:
            return self._result(call.id, decision.message, is_error=True)
        try:
            validate(instance=arguments, schema=tool.parameters)
        except ValidationError as exc:
            result = self._result(
                call.id,
                f"argument validation failed: {exc.message}",
                is_error=True,
            )
            after = self.guardrails.after_call(
                call.name,
                arguments,
                result.content,
                failed=True,
            )
            if after.action == "warn":
                result.content = append_guardrail_guidance(result.content, after)
            return result
        executor: concurrent.futures.ThreadPoolExecutor | None = None
        try:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(tool.execute, **arguments)
            output = future.result(timeout=tool.timeout_s)
            executor.shutdown(wait=True)
            result = self._result(call.id, output, is_error=False)
        except concurrent.futures.TimeoutError:
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            result = self._result(call.id, f"tool timed out after {tool.timeout_s}s", is_error=True)
        except Exception:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
            err = traceback.format_exc(limit=5)
            result = self._result(call.id, err, is_error=True)
        after = self.guardrails.after_call(
            call.name,
            arguments,
            result.content,
            failed=result.is_error,
        )
        if after.action == "warn":
            result.content = append_guardrail_guidance(result.content, after)
        return result

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
