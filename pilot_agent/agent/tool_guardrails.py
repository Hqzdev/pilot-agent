from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

IDEMPOTENT_TOOLS = frozenset(
    {
        "read_file",
        "list_files",
        "web_search",
        "web_fetch",
        "load_skill",
        "ask_user",
    }
)
MUTATING_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "bash",
        "run_and_check",
        "save_skill",
        "complete_phase",
    }
)


@dataclass(frozen=True)
class ToolGuardrailConfig:
    warnings_enabled: bool = True
    hard_stop_enabled: bool = False
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5
    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5
    idempotent_tools: frozenset[str] = field(default_factory=lambda: IDEMPOTENT_TOOLS)
    mutating_tools: frozenset[str] = field(default_factory=lambda: MUTATING_TOOLS)


@dataclass(frozen=True)
class ToolCallSignature:
    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: Mapping[str, Any] | None) -> ToolCallSignature:
        raw = json.dumps(
            args or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return cls(tool_name=tool_name, args_hash=hashlib.sha256(raw.encode()).hexdigest()[:16])


@dataclass(frozen=True)
class ToolGuardrailDecision:
    action: str = "allow"
    code: str = "allow"
    message: str = ""
    tool_name: str = ""
    count: int = 0
    signature: ToolCallSignature | None = None

    @property
    def allows_execution(self) -> bool:
        return self.action in {"allow", "warn"}

    @property
    def should_halt(self) -> bool:
        return self.action in {"block", "halt"}


class ToolCallGuardrailController:
    def __init__(self, config: ToolGuardrailConfig | None = None):
        self.config = config or ToolGuardrailConfig()
        self.reset_for_turn()

    def reset_for_turn(self) -> None:
        self._exact_failure_counts: dict[ToolCallSignature, int] = {}
        self._same_tool_failure_counts: dict[str, int] = {}
        self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
        self.halt_decision: ToolGuardrailDecision | None = None

    def before_call(self, tool_name: str, args: Mapping[str, Any] | None) -> ToolGuardrailDecision:
        signature = ToolCallSignature.from_call(tool_name, args)
        if not self.config.hard_stop_enabled:
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)
        exact = self._exact_failure_counts.get(signature, 0)
        if exact >= self.config.exact_failure_block_after:
            return self._halt(
                "block",
                "repeated_exact_failure_block",
                tool_name,
                exact,
                signature,
                f"Blocked {tool_name}: same arguments failed {exact} times. Change strategy.",
            )
        if self._is_idempotent(tool_name):
            previous = self._no_progress.get(signature)
            if previous and previous[1] >= self.config.no_progress_block_after:
                return self._halt(
                    "block",
                    "idempotent_no_progress_block",
                    tool_name,
                    previous[1],
                    signature,
                    (
                        f"Blocked {tool_name}: same read-only call returned the same "
                        f"result {previous[1]} times."
                    ),
                )
        return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        *,
        failed: bool,
    ) -> ToolGuardrailDecision:
        signature = ToolCallSignature.from_call(tool_name, args)
        if failed:
            exact = self._exact_failure_counts.get(signature, 0) + 1
            self._exact_failure_counts[signature] = exact
            self._no_progress.pop(signature, None)
            same = self._same_tool_failure_counts.get(tool_name, 0) + 1
            self._same_tool_failure_counts[tool_name] = same
            if self.config.hard_stop_enabled and same >= self.config.same_tool_failure_halt_after:
                return self._halt(
                    "halt",
                    "same_tool_failure_halt",
                    tool_name,
                    same,
                    signature,
                    (
                        f"Stopped {tool_name}: it failed {same} times this turn. "
                        "Diagnose before retrying."
                    ),
                )
            if self.config.warnings_enabled and exact >= self.config.exact_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="repeated_exact_failure_warning",
                    message=(
                        f"{tool_name} failed {exact} times with identical arguments. "
                        "Do not retry unchanged; inspect the error and change strategy."
                    ),
                    tool_name=tool_name,
                    count=exact,
                    signature=signature,
                )
            if self.config.warnings_enabled and same >= self.config.same_tool_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=(
                        f"{tool_name} failed {same} times this turn. "
                        "Try a smaller diagnostic or different tool."
                    ),
                    tool_name=tool_name,
                    count=same,
                    signature=signature,
                )
            return ToolGuardrailDecision(tool_name=tool_name, count=exact, signature=signature)

        self._exact_failure_counts.pop(signature, None)
        self._same_tool_failure_counts.pop(tool_name, None)
        if not self._is_idempotent(tool_name):
            self._no_progress.pop(signature, None)
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)
        result_hash = hashlib.sha256((result or "").encode()).hexdigest()[:16]
        previous = self._no_progress.get(signature)
        count = previous[1] + 1 if previous and previous[0] == result_hash else 1
        self._no_progress[signature] = (result_hash, count)
        if self.config.warnings_enabled and count >= self.config.no_progress_warn_after:
            return ToolGuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=(
                    f"{tool_name} returned the same result {count} times. "
                    "Use the result already provided or change the query."
                ),
                tool_name=tool_name,
                count=count,
                signature=signature,
            )
        return ToolGuardrailDecision(tool_name=tool_name, count=count, signature=signature)

    def _halt(
        self,
        action: str,
        code: str,
        tool_name: str,
        count: int,
        signature: ToolCallSignature,
        message: str,
    ) -> ToolGuardrailDecision:
        decision = ToolGuardrailDecision(action, code, message, tool_name, count, signature)
        self.halt_decision = decision
        return decision

    def _is_idempotent(self, tool_name: str) -> bool:
        if tool_name in self.config.mutating_tools:
            return False
        return tool_name in self.config.idempotent_tools


def append_guardrail_guidance(result: str, decision: ToolGuardrailDecision) -> str:
    if decision.action != "warn" or not decision.message:
        return result
    return f"{result}\n\n[Tool loop warning: {decision.code}; {decision.message}]"
