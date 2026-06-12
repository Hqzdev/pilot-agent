from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from operator import methodcaller
from pathlib import Path
from typing import Protocol, cast

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from devagent.agent.context import ContextManager, build_system_prompt
from devagent.agent.memory import Memory, SkillOutcomeRecorder
from devagent.agent.phases import PHASES, Phase
from devagent.agent.state import read_state, write_session_record
from devagent.agent.types import Message, Role, ToolCall, ToolResult
from devagent.providers.base import Provider
from devagent.tools.base import ToolRegistry


def emit(console: Console, *objects: object) -> None:
    methodcaller("print", *objects)(console)


class SkillIndex(Protocol):
    def index_for_prompt(self, phase: str, stack: list[str]) -> str: ...


@dataclass
class EmptySkills:
    def index_for_prompt(self, phase: str, stack: list[str]) -> str:
        return ""


@dataclass
class RichUI:
    console: Console = field(default_factory=Console)

    def render(self, message: Message) -> None:
        if message.content:
            emit(self.console, message.content)
        for call in message.tool_calls:
            emit(self.console, f"⚙ {call.name}: {call.arguments}")

    def render_phase(self, phase: Phase) -> None:
        emit(self.console, Panel(f"Current phase: {phase.name}", title="DevAgent"))

    def prompt_user(self) -> str:
        return self.console.input("> ")

    def api_spinner(self) -> Progress:
        return Progress(SpinnerColumn(), TextColumn("Calling provider..."), console=self.console)


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
        ui: RichUI | None = None,
        history: list[Message] | None = None,
        phase_name: str = "discovery",
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
        self.ui = ui or RichUI()
        self.history = history or []
        self.memory.end_of_session(self.history)
        self.phase: Phase | None = PHASES[phase_name]
        self.stack = stack or []
        self.loaded_skills: dict[str, set[str]] = {}
        self.model_switcher = model_switcher

    def run(self, max_turns: int = 200) -> None:
        turns = 0
        while self.phase is not None and turns < max_turns:
            self.run_turn()
            turns += 1

    def run_turn(self) -> None:
        if self.phase is None:
            return
        phase = self.phase
        state_md = read_state(self.project_root)
        system = build_system_prompt(
            phase.prompt,
            state_md,
            self.skills.index_for_prompt(phase.name, self.stack),
            self.memory.relevant_lessons(self.stack),
        )
        messages = self.ctx.prepare(system, self.history)
        with self.ui.api_spinner() as progress:
            progress.add_task("api", total=None)
            resp = self.provider.complete(system, messages, self.registry.specs(phase.tools))
        resp.message.phase = phase.name
        self.history.append(resp.message)
        write_session_record(self.project_root, resp.message)
        self.ui.render(resp.message)
        if resp.stop_reason == "tool_use":
            results: list[ToolResult] = []
            pin_tool_message = False
            for call in resp.message.tool_calls:
                if call.name == "complete_phase":
                    results.append(self.advance_phase(call))
                    continue
                result = self.registry.execute(call)
                self.memory.observe(call, result)
                if call.name == "load_skill" and not result.is_error:
                    skill_name = str(call.arguments.get("name", ""))
                    self.loaded_skills.setdefault(phase.name, set()).add(skill_name)
                    pin_tool_message = True
                results.append(result)
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

    def handle_slash_command(self, raw: str) -> bool:
        command, _, arg = raw.partition(" ")
        if command == "/help":
            self.ui.console.print(
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
                self.ui.console.print("Usage: /model <provider>:<model>")
                return True
            if self.model_switcher is None:
                self.ui.console.print("Model switching is not configured in this session")
                return True
            provider = self.model_switcher(arg)
            self.provider = provider
            self.ctx.replace_provider(provider)
            write_session_record(self.project_root, {"_type": "model_change", "target": arg})
            self.ui.console.print(f"✓ model switched to {arg}")
        elif command == "/skip":
            result = self.advance_phase(
                ToolCall(
                    id="slash-skip",
                    name="complete_phase",
                    arguments={"summary": "Skipped by user"},
                )
            )
            self.ui.console.print(result.content)
        elif command == "/compact":
            self.history = self.ctx.compact("", self.history)
            self.ui.console.print("context compacted")
        elif command == "/usage":
            tokens = self.provider.count_tokens("", self.history)
            self.ui.console.print(f"tokens: {tokens}")
        elif command == "/state":
            self.ui.console.print(read_state(self.project_root))
        elif command == "/skills":
            phase_name = self.phase.name if self.phase else "none"
            self.ui.console.print(self.skills.index_for_prompt(phase_name, self.stack))
        elif command == "/undo":
            removed = self._undo_last_turn()
            write_session_record(self.project_root, {"_type": "undo", "removed_messages": removed})
            self.ui.console.print(
                f"undid {removed} messages; file changes were not reverted"
            )
        elif command == "/quit":
            write_session_record(self.project_root, {"_type": "quit"})
            self.phase = None
            self.ui.console.print("saved; exiting")
        else:
            self.ui.console.print(f"Unknown slash command: {command}. Run /help")
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
        state_path = self.project_root / ".devagent" / "STATE.md"
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
        return ToolResult(tool_call_id=call.id, content=f"completed phase {current.name}")

    def _summarize_lesson(self, prompt: str) -> str:
        response = self.provider.complete(prompt, messages=[], tools=[], max_tokens=512)
        return response.message.content


def restore_phase_from_session(project_root: Path) -> str:
    session = project_root / ".devagent" / "session.jsonl"
    phase = "discovery"
    if not session.exists():
        return phase
    for line in session.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if data.get("_type") == "phase_change":
            phase = data.get("to") or phase
    return phase
