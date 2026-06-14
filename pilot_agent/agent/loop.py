from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from pilot_agent.agent.context import ContextManager, build_system_prompt
from pilot_agent.agent.iteration_budget import IterationBudget
from pilot_agent.agent.memory import Memory, SkillOutcomeRecorder
from pilot_agent.agent.phases import PHASES, Phase
from pilot_agent.agent.session_lock import ProjectSessionLock
from pilot_agent.agent.state import read_state, write_session_record
from pilot_agent.agent.types import (
    CompletionResponse,
    Message,
    Role,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from pilot_agent.agent.usage import SessionUsage, normalize_usage
from pilot_agent.cli.ui import UI
from pilot_agent.providers.base import Provider
from pilot_agent.tools.base import ToolRegistry


class SkillIndex(Protocol):
    def index_for_prompt(self, phase: str, stack: list[str]) -> str: ...


@dataclass
class EmptySkills:
    def index_for_prompt(self, phase: str, stack: list[str]) -> str:
        return ""


class AgentLoop:
    def __init__(
        self,
        *,
        project_root: Path,
        provider: Provider,
        registry: ToolRegistry,
        ctx: ContextManager,
        skills: SkillIndex | None = None,
        memory: Memory | None = None,
        ui: UI | None = None,
        history: list[Message] | None = None,
        phase_name: str | None = "discovery",
        stack: list[str] | None = None,
        model_switcher: Callable[[str], Provider] | None = None,
    ):
        self.project_root = project_root.resolve()
        self.provider = provider
        self.registry = registry
        self.ctx = ctx
        self.skills = skills or EmptySkills()
        recorder = (
            cast(SkillOutcomeRecorder, self.skills)
            if callable(getattr(self.skills, "record_outcome", None))
            else None
        )
        self.memory = memory or Memory(
            summarizer=self._summarize_lesson,
            skill_recorder=recorder,
        )
        self.ui = ui or UI()
        self.history = history or []
        self.memory.end_of_session(self.history)
        self.phase: Phase | None = PHASES[phase_name] if phase_name is not None else None
        self.stack = stack or []
        self.loaded_skills: dict[str, set[str]] = {}
        self.model_switcher = model_switcher
        self.usage = SessionUsage()

    def run(self, max_turns: int = 200) -> None:
        with ProjectSessionLock(self.project_root):
            budget = IterationBudget(max_turns)
            interrupts = 0
            while self.phase is not None:
                if not budget.consume():
                    write_session_record(
                        self.project_root,
                        {
                            "_type": "iteration_budget_exhausted",
                            "limit": budget.limit,
                            "consumed": budget.consumed,
                        },
                    )
                    self.ui.warning(f"iteration budget exhausted after {budget.consumed} turns")
                    break
                try:
                    self.run_turn()
                    interrupts = 0
                except KeyboardInterrupt:
                    budget.refund()
                    interrupts += 1
                    if interrupts >= 2:
                        write_session_record(
                            self.project_root,
                            {"_type": "interrupt", "count": interrupts},
                        )
                        self.ui.warning("interrupted twice; saved session and exiting")
                        break
                    self.ui.warning(
                        "interrupted - enter a new instruction or /quit; "
                        "a second Ctrl+C exits the session"
                    )

    def run_turn(self) -> None:
        if self.phase is None:
            return
        self.registry.guardrails.reset_for_turn()
        phase = self.phase
        state_md = read_state(self.project_root)
        system = build_system_prompt(
            phase.prompt,
            state_md,
            self.skills.index_for_prompt(phase.name, self.stack),
            self.memory.relevant_lessons(self.stack),
        )
        messages = self.ctx.prepare(system, self.history)
        tools = self.registry.specs(phase.tools, context_window=self.provider.context_window)
        with self.ui.api_spinner() as progress:
            progress.add_task("api", total=None)
            resp = self._complete_with_hooks(system, messages, tools, phase)
        usage = normalize_usage(resp.usage)
        self.usage.add(
            usage,
            provider=self.provider.__class__.__name__.removesuffix("Provider").lower(),
            model=self.provider.model,
        )
        resp.message.tokens = usage.total_tokens
        resp.message.phase = phase.name
        self.history.append(resp.message)
        write_session_record(self.project_root, resp.message)
        self.ui.render(resp.message)
        if resp.stop_reason == "tool_use":
            results, pin_tool_message = self._execute_tool_calls(phase, resp.message.tool_calls)
            current_phase = self.phase.name if self.phase is not None else None
            tool_msg = Message(
                role=Role.TOOL,
                tool_results=results,
                pinned=pin_tool_message,
                phase=current_phase,
            )
            self.history.append(tool_msg)
            write_session_record(self.project_root, tool_msg)
        else:
            user_input = self.ui.prompt_user()
            if user_input.strip().startswith("/"):
                self.handle_slash_command(user_input.strip())
                return
            user_msg = Message(role=Role.USER, content=user_input, phase=phase.name)
            self.history.append(user_msg)
            write_session_record(self.project_root, user_msg)

    def _complete_with_hooks(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        phase: Phase,
    ) -> CompletionResponse:
        context = self._runtime_context(phase)
        request: dict[str, Any] = {
            "system": system,
            "messages": messages,
            "tools": tools,
            "max_tokens": 4096,
        }
        self.registry.hooks.invoke_hook("pre_llm_call", **request, **context)
        request_mw = self.registry.hooks.apply_llm_request_middleware(request, **context)
        payload = request_mw.payload if isinstance(request_mw.payload, dict) else request
        started_at = time.monotonic()

        def invoke_provider(next_request: Any) -> CompletionResponse:
            typed = _coerce_llm_request(next_request, fallback=request)
            return self.provider.complete(
                typed["system"],
                typed["messages"],
                typed["tools"],
                max_tokens=typed["max_tokens"],
            )

        try:
            response = self.registry.hooks.run_llm_execution_middleware(
                payload,
                invoke_provider,
                **context,
                middleware_trace=request_mw.trace,
            )
        except Exception as exc:
            self.registry.hooks.invoke_hook(
                "api_request_error",
                error=str(exc),
                error_type=exc.__class__.__name__,
                **context,
            )
            raise
        if not isinstance(response, CompletionResponse):
            raise TypeError("llm execution middleware must return CompletionResponse")
        self.registry.hooks.invoke_hook(
            "post_llm_call",
            stop_reason=response.stop_reason,
            usage=response.usage,
            tool_call_count=len(response.message.tool_calls),
            duration_ms=int((time.monotonic() - started_at) * 1000),
            **context,
        )
        return response

    def _execute_tool_calls(
        self,
        phase: Phase,
        calls: list[ToolCall],
    ) -> tuple[list[ToolResult], bool]:
        results: list[ToolResult] = []
        pin_tool_message = False
        pending: list[ToolCall] = []

        def flush_pending() -> None:
            nonlocal pin_tool_message
            if not pending:
                return
            executions = self.registry.execute_batch(
                list(pending),
                context=self._runtime_context(phase),
            )
            pending.clear()
            for execution in executions:
                call = execution.call
                result = execution.result
                self.memory.observe(call, result)
                self.ui.render_tool_result(call, result, elapsed_s=execution.elapsed_s)
                if call.name == "load_skill" and not result.is_error:
                    skill_name = str(call.arguments.get("name", ""))
                    self.loaded_skills.setdefault(phase.name, set()).add(skill_name)
                    pin_tool_message = True
                results.append(result)

        for call in calls:
            if call.name == "complete_phase":
                flush_pending()
                results.append(self.advance_phase(call))
                continue
            pending.append(call)
        flush_pending()
        return results, pin_tool_message

    def _runtime_context(self, phase: Phase) -> dict[str, Any]:
        provider_name = self.provider.__class__.__name__.removesuffix("Provider").lower()
        return {
            "phase": phase.name,
            "allowed_tools": list(phase.tools),
            "project_root": str(self.project_root),
            "provider": provider_name,
            "model": self.provider.model,
        }

    def handle_slash_command(self, raw: str) -> bool:
        command, _, arg = raw.partition(" ")
        if command == "/help":
            self.ui.notice(
                "/model <provider>:<model>\n"
                "/skip\n"
                "/compact\n"
                "/usage\n"
                "/state\n"
                "/skills\n"
                "/undo\n"
                "/quit"
            )
        elif command == "/model":
            if not arg:
                self.ui.warning("Usage: /model <provider>:<model>")
                return True
            if self.model_switcher is None:
                self.ui.warning("Model switching is not configured in this session")
                return True
            provider = self.model_switcher(arg)
            self.provider = provider
            self.ctx.replace_provider(provider)
            write_session_record(self.project_root, {"_type": "model_change", "target": arg})
            self.ui.success(f"model switched to {arg}")
        elif command == "/skip":
            result = self.advance_phase(
                ToolCall(
                    id="slash-skip",
                    name="complete_phase",
                    arguments={"summary": "Skipped by user"},
                )
            )
            self.ui.notice(result.content)
        elif command == "/compact":
            self.history = self.ctx.compact("", self.history)
            self.ui.warning("context compacted")
        elif command == "/usage":
            context_tokens = self.provider.count_tokens("", self.history)
            self.ui.notice(f"{self.usage.summary()}\ncurrent context tokens: {context_tokens}")
        elif command == "/state":
            self.ui.notice(read_state(self.project_root))
        elif command == "/skills":
            phase_name = self.phase.name if self.phase else "none"
            self.ui.notice(self.skills.index_for_prompt(phase_name, self.stack))
        elif command == "/undo":
            removed = self._undo_last_turn()
            write_session_record(self.project_root, {"_type": "undo", "removed_messages": removed})
            self.ui.warning(
                f"undid {removed} messages; file changes were not reverted"
            )
        elif command == "/quit":
            write_session_record(self.project_root, {"_type": "quit"})
            self.phase = None
            self.ui.notice("saved; exiting")
        else:
            self.ui.warning(f"Unknown slash command: {command}. Run /help")
        return True

    def _undo_last_turn(self) -> int:
        removed = 0
        while self.history and removed < 2 and self.history[-1].role in {Role.ASSISTANT, Role.TOOL}:
            self.history.pop()
            removed += 1
        return removed

    def advance_phase(self, call: ToolCall) -> ToolResult:
        if self.phase is None:
            return ToolResult(tool_call_id=call.id, content="no active phase", is_error=True)
        summary = str(call.arguments.get("summary", ""))
        state_path = self.project_root / ".pilot-agent" / "STATE.md"
        existing = state_path.read_text(encoding="utf-8")
        state_path.write_text(existing + f"\n\n## Phase {self.phase.name} summary\n{summary}\n")
        before_memory = len(self.history)
        self.memory.end_of_phase(self.phase.name, self.history)
        for message in self.history[before_memory:]:
            write_session_record(self.project_root, message)
        if self.phase.name == "deploy" and len(self.history) > before_memory:
            return ToolResult(
                tool_call_id=call.id,
                content="deploy skill synthesis requested; phase remains deploy",
            )
        for message in self.history:
            if message.phase == self.phase.name:
                message.pinned = False
        recorder = getattr(self.skills, "record_outcome", None)
        if callable(recorder):
            for skill_name in self.loaded_skills.get(self.phase.name, set()):
                recorder(skill_name, True)
        current = self.phase
        next_name = current.next
        write_session_record(
            self.project_root,
            {"_type": "phase_change", "from": current.name, "to": next_name},
        )
        self.phase = PHASES[next_name] if next_name is not None else None
        self.ui.phase_transition(current.name, next_name, summary)
        return ToolResult(tool_call_id=call.id, content=f"completed phase {current.name}")

    def _summarize_lesson(self, prompt: str) -> str:
        response = self.provider.complete(prompt, messages=[], tools=[], max_tokens=512)
        return response.message.content


def _coerce_llm_request(
    request: Any,
    *,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    raw = request if isinstance(request, dict) else fallback
    system = raw.get("system", fallback["system"])
    messages = raw.get("messages", fallback["messages"])
    tools = raw.get("tools", fallback["tools"])
    max_tokens = raw.get("max_tokens", fallback["max_tokens"])
    if not isinstance(system, str):
        system = fallback["system"]
    if not isinstance(messages, list):
        messages = fallback["messages"]
    if not isinstance(tools, list):
        tools = fallback["tools"]
    try:
        typed_max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        typed_max_tokens = int(fallback["max_tokens"])
    return {
        "system": system,
        "messages": cast(list[Message], messages),
        "tools": cast(list[ToolSpec], tools),
        "max_tokens": typed_max_tokens,
    }


def restore_phase_from_session(project_root: Path) -> str | None:
    session = project_root / ".pilot-agent" / "session.jsonl"
    phase: str | None = "discovery"
    if not session.exists():
        return phase
    for line in session.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if data.get("_type") == "phase_change":
            phase = data.get("to")
    return phase
