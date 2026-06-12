"""Rendering facade for agent messages, tool rows, phase transitions, and notices."""

from __future__ import annotations

import json
import re
import shutil
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.text import Text

from pilot_agent.agent.phases import Phase
from pilot_agent.agent.types import Message, ToolCall, ToolResult
from pilot_agent.cli.ui.components import create_console
from pilot_agent.cli.ui.input import PilotAgentInput
from pilot_agent.cli.ui.status import StatusBar
from pilot_agent.cli.ui.theme import Glyphs, glyphs


def _truncate_middle(value: str, max_len: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= max_len:
        return clean
    if max_len <= 3:
        return clean[:max_len]
    return clean[: max_len - 1] + "…"


def _first_argument(call: ToolCall) -> str:
    keys = ["command", "path", "name", "question", "summary", "content"]
    for key in keys:
        value = call.arguments.get(key)
        if isinstance(value, str) and value:
            return value
    if call.arguments:
        first = next(iter(call.arguments.values()))
        return json.dumps(first, ensure_ascii=False) if not isinstance(first, str) else first
    return ""


def _exit_code(content: str) -> int | None:
    match = re.search(r"^\[exit (\d+)\]", content)
    return int(match.group(1)) if match else None


def _line_delta(content: str) -> str | None:
    match = re.search(r"\+(\d+)\s+-([0-9]+)", content)
    return f"+{match.group(1)} -{match.group(2)}" if match else None


def _tail_lines(content: str, limit: int = 6) -> list[str]:
    lines = [line for line in content.splitlines() if line.strip()]
    return lines[-limit:]


@dataclass
class ToolTimer:
    call: ToolCall
    started_at: float = field(default_factory=monotonic)

    def elapsed(self) -> float:
        return monotonic() - self.started_at


class SpinnerContext(AbstractContextManager[Progress]):
    def __init__(self, console: Console, text: str):
        self.progress = Progress(
            SpinnerColumn(Glyphs.SPINNER, style="pilot_agent.muted"),
            TextColumn(text, style="pilot_agent.muted"),
            console=console,
            transient=True,
        )

    def __enter__(self) -> Progress:
        return self.progress.__enter__()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        self.progress.__exit__(exc_type, exc, tb)
        return None


class Renderer:
    def __init__(self, console: Console):
        self.console = console

    def render_agent(self, content: str) -> None:
        if content:
            self.console.print()
            self.console.print(Markdown(content))

    def render_message(self, message: Message) -> None:
        self.render_agent(message.content)
        if message.tool_calls:
            for call in message.tool_calls:
                self.render_tool_call(call)

    def render_tool_call(self, call: ToolCall) -> None:
        g = glyphs()
        arg = _truncate_middle(_first_argument(call), self._argument_width())
        self.console.print(Text(f"{g.TOOL} {call.name} · {arg}", style="pilot_agent.muted"))

    def render_tool_result(
        self,
        call: ToolCall,
        result: ToolResult,
        *,
        elapsed_s: float = 0,
    ) -> None:
        g = glyphs()
        arg = _truncate_middle(_first_argument(call), self._argument_width())
        exit_code = _exit_code(result.content)
        ok = not result.is_error and (exit_code is None or exit_code == 0)
        status_glyph = g.OK if ok else g.ERR
        status_style = "pilot_agent.ok" if ok else "pilot_agent.err"
        name = "skill" if call.name == "load_skill" else call.name
        suffix = self._tool_suffix(call, result, exit_code)
        line = Text(f"{g.TOOL} {name} · ", style="pilot_agent.muted")
        arg_style = "pilot_agent.accent" if call.name == "load_skill" else "pilot_agent.muted"
        line.append(arg, style=arg_style)
        line.append(" · ", style="pilot_agent.muted")
        line.append(status_glyph, style=status_style)
        line.append(f" {suffix} · {elapsed_s:.1f}s", style="pilot_agent.muted")
        delta = _line_delta(result.content)
        if delta and call.name in {"write_file", "edit_file"}:
            line.append(f" · {delta}", style="pilot_agent.info")
        self.console.print(line)
        if not ok:
            self.render_error_tail(result.content)

    def render_error_tail(self, content: str) -> None:
        for line in _tail_lines(content):
            tail = Text("│ ", style="pilot_agent.muted")
            tail.append(line, style="pilot_agent.err")
            self.console.print(tail)

    def render_phase_transition(
        self,
        *,
        phase: str,
        next_phase: str | None,
        summary: str,
    ) -> None:
        g = glyphs()
        self.console.print(Rule(style="pilot_agent.accent.dim"))
        self.console.print(
            Text.assemble(
                (f"{g.PHASE} Phase · {phase} ", "pilot_agent.accent"),
                (f"{g.ARROW} ", "pilot_agent.muted"),
                (g.OK, "pilot_agent.ok"),
                (" complete", "pilot_agent.muted"),
            )
        )
        if summary:
            self.console.print(Text(_truncate_middle(summary, 100), style="pilot_agent.muted"))
        if next_phase:
            self.console.print(
                Text(
                    f"{g.PHASE} Phase · {next_phase} — starting",
                    style="pilot_agent.accent",
                )
            )
        self.console.print(Rule(style="pilot_agent.accent.dim"))

    def _tool_suffix(self, call: ToolCall, result: ToolResult, exit_code: int | None) -> str:
        if call.name == "load_skill":
            return "loaded" if not result.is_error else "failed"
        if call.name == "run_and_check":
            return self._run_check_suffix(result)
        if exit_code is not None:
            return f"exit {exit_code}"
        return "ok" if not result.is_error else "error"

    def _run_check_suffix(self, result: ToolResult) -> str:
        try:
            data = json.loads(result.content)
        except json.JSONDecodeError:
            return "check"
        verdict = data.get("verdict")
        return str(verdict) if verdict else "check"

    def _argument_width(self) -> int:
        width = shutil.get_terminal_size((100, 24)).columns
        return max(16, width - 45)


class UI:
    def __init__(
        self,
        *,
        console: Console | None = None,
        color: str = "auto",
        show_status: bool = True,
        history_path: Path | None = None,
        skill_names: list[str] | None = None,
    ):
        self.console = console or create_console(color=color)
        self.renderer = Renderer(self.console)
        self.status = StatusBar(self.console, enabled=show_status)
        self.input = PilotAgentInput(history_path=history_path, skill_names=skill_names or [])

    def render(self, message: Message) -> None:
        self.renderer.render_message(message)

    def render_phase(self, phase: Phase) -> None:
        self.notice(f"Phase: {phase.name}")

    def prompt_user(self) -> str:
        return self.input.prompt()

    def api_spinner(self) -> SpinnerContext:
        return SpinnerContext(self.console, "thinking")

    def tool_timer(self, call: ToolCall) -> ToolTimer:
        return ToolTimer(call)

    def render_tool_result(self, call: ToolCall, result: ToolResult, elapsed_s: float = 0) -> None:
        self.renderer.render_tool_result(call, result, elapsed_s=elapsed_s)

    def phase_transition(self, phase: str, next_phase: str | None, summary: str) -> None:
        self.renderer.render_phase_transition(phase=phase, next_phase=next_phase, summary=summary)

    def notice(self, text: str) -> None:
        self.console.print(Text(text, style="pilot_agent.muted"))

    def success(self, text: str) -> None:
        self.console.print(Text(text, style="pilot_agent.ok"))

    def warning(self, text: str) -> None:
        self.console.print(Text(text, style="pilot_agent.warn"))

    def error(self, text: str) -> None:
        self.console.print(Text(text, style="pilot_agent.err"))

    def live_status(self, text: str) -> Live:
        return self.status.live(text)
