"""prompt_toolkit input session with slash completion, history, and non-tty fallback."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from rich.prompt import Confirm, IntPrompt, Prompt

from pilot_agent.cli.ui.theme import Palette, glyphs

SLASH_COMMANDS: dict[str, str] = {
    "/model": "switch model mid-session",
    "/skip": "move to the next phase",
    "/compact": "force context compaction",
    "/usage": "show tokens and cost",
    "/state": "show STATE.md",
    "/skills": "show skills for the current phase",
    "/undo": "remove the last assistant/tool pair from history",
    "/help": "show slash commands",
    "/quit": "save and exit",
}


class SlashCompleter(Completer):
    def __init__(self, *, skill_names: list[str] | None = None):
        self.skill_names = skill_names or []

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterator[Completion]:
        del complete_event
        text = document.text_before_cursor
        if text.startswith("/skills "):
            prefix = text.removeprefix("/skills ").lower()
            for name in self.skill_names:
                if name.lower().startswith(prefix):
                    yield Completion(name, start_position=-len(prefix), display_meta="skill")
            return
        if text.startswith("/"):
            prefix = text.lower()
            for command, description in SLASH_COMMANDS.items():
                if command.startswith(prefix):
                    yield Completion(
                        command,
                        start_position=-len(text),
                        display_meta=description,
                    )


def _bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    @bindings.add("escape", "c-m")
    def _(event: KeyPressEvent) -> None:
        event.current_buffer.insert_text("\n")

    @bindings.add("enter")
    def _(event: KeyPressEvent) -> None:
        event.current_buffer.validate_and_handle()

    return bindings


@dataclass
class PilotAgentInput:
    history_path: Path | None = None
    skill_names: list[str] | None = None

    def __post_init__(self) -> None:
        self.completer = SlashCompleter(skill_names=self.skill_names or [])
        current = f"bg:{Palette.ACCENT_DIM} {Palette.USER}"
        self.style = Style.from_dict(
            {
                "completion-menu.completion.current": current,
                "completion-menu.meta.completion.current": current,
                "choice.prompt": Palette.USER,
                "choice.selected": f"bold {Palette.ACCENT}",
                "choice.normal": Palette.USER,
                "choice.hint": Palette.MUTED,
            }
        )

    def prompt(
        self,
        message: str | None = None,
        *,
        password: bool = False,
        default: str | None = None,
        choices: list[str] | None = None,
    ) -> str:
        if not sys.stdin.isatty():
            return self._fallback_prompt(
                message,
                password=password,
                default=default,
                choices=choices,
            )
        prompt_message = message if message is not None else f"{glyphs().PROMPT} "
        session: PromptSession[str] = PromptSession(
            history=FileHistory(str(self.history_path)) if self.history_path else None,
            completer=self.completer,
            complete_while_typing=True,
            multiline=True,
            key_bindings=_bindings(),
            style=self.style,
        )
        answer = session.prompt(prompt_message, is_password=password, default=default or "")
        if choices and answer not in choices:
            return self.prompt(message, password=password, default=default, choices=choices)
        return answer

    def confirm(self, message: str, *, default: bool = False) -> bool:
        if not sys.stdin.isatty():
            return Confirm.ask(message, default=default)
        answer = self.prompt(message, default="Y" if default else "n")
        return answer.strip().lower() in {"y", "yes", "1", "true"}

    def ask_int(self, message: str, *, default: int, choices: list[str] | None = None) -> int:
        if not sys.stdin.isatty():
            return int(IntPrompt.ask(message, default=default, choices=choices))
        answer = self.prompt(message, default=str(default), choices=choices)
        return int(answer)

    def select(
        self,
        message: str,
        choices: list[tuple[str, str]],
        *,
        default: int = 0,
    ) -> str:
        if not choices:
            raise ValueError("select requires at least one choice")
        default = max(0, min(default, len(choices) - 1))
        if not sys.stdin.isatty():
            return self._fallback_select(message, choices, default)
        selected = [default]
        g = glyphs()

        def formatted_choices() -> list[tuple[str, str]]:
            fragments: list[tuple[str, str]] = [("class:choice.prompt", f"{message}\n")]
            for idx, (_, label) in enumerate(choices):
                if idx == selected[0]:
                    fragments.append(("class:choice.selected", f"{g.PROMPT} {label}\n"))
                else:
                    fragments.append(("class:choice.normal", f"  {label}\n"))
            fragments.append(("class:choice.hint", "↑/↓ choose · Enter select\n"))
            return fragments

        bindings = KeyBindings()

        @bindings.add("up")
        @bindings.add("k")
        def _up(event: KeyPressEvent) -> None:
            selected[0] = (selected[0] - 1) % len(choices)
            event.app.invalidate()

        @bindings.add("down")
        @bindings.add("j")
        def _down(event: KeyPressEvent) -> None:
            selected[0] = (selected[0] + 1) % len(choices)
            event.app.invalidate()

        @bindings.add("enter")
        def _enter(event: KeyPressEvent) -> None:
            event.app.exit(result=choices[selected[0]][0])

        @bindings.add("c-c")
        def _interrupt(event: KeyPressEvent) -> None:
            event.app.exit(exception=KeyboardInterrupt())

        control: Any = FormattedTextControl(formatted_choices, focusable=True)
        app: Application[str] = Application(
            layout=Layout(Window(control, height=len(choices) + 2, always_hide_cursor=True)),
            key_bindings=bindings,
            mouse_support=True,
            full_screen=False,
            style=self.style,
        )
        return app.run()

    def _fallback_select(
        self,
        message: str,
        choices: list[tuple[str, str]],
        default: int,
    ) -> str:
        prompt_message = message + "\n" + "\n".join(
            f"  {idx}. {label}" for idx, (_, label) in enumerate(choices, start=1)
        )
        answer = IntPrompt.ask(
            prompt_message,
            default=default + 1,
            choices=[str(idx) for idx in range(1, len(choices) + 1)],
        )
        return choices[answer - 1][0]

    def _fallback_prompt(
        self,
        message: str | None,
        *,
        password: bool,
        default: str | None,
        choices: list[str] | None,
    ) -> str:
        if choices:
            return Prompt.ask(
                message or "",
                password=password,
                default=default or "",
                choices=choices,
            )
        return Prompt.ask(message or "", password=password, default=default or "")
