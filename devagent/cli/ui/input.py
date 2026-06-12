"""prompt_toolkit input session with slash completion, history, and non-tty fallback."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.styles import Style
from rich.prompt import Confirm, IntPrompt, Prompt

from devagent.cli.ui.theme import Palette, glyphs

SLASH_COMMANDS: dict[str, str] = {
    "/model": "сменить модель на лету",
    "/skip": "перейти к следующей фазе",
    "/compact": "принудительно сжать контекст",
    "/usage": "показать токены и стоимость",
    "/state": "показать STATE.md",
    "/skills": "показать skills текущей фазы",
    "/undo": "откатить последнюю пару assistant/tool в истории",
    "/help": "показать slash-команды",
    "/quit": "сохранить и выйти",
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
class DevAgentInput:
    history_path: Path | None = None
    skill_names: list[str] | None = None

    def __post_init__(self) -> None:
        self.completer = SlashCompleter(skill_names=self.skill_names or [])
        current = f"bg:{Palette.ACCENT_DIM} {Palette.USER}"
        self.style = Style.from_dict(
            {
                "completion-menu.completion.current": current,
                "completion-menu.meta.completion.current": current,
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
        return answer.strip().lower() in {"y", "yes", "д", "да", "1", "true"}

    def ask_int(self, message: str, *, default: int, choices: list[str] | None = None) -> int:
        if not sys.stdin.isatty():
            return int(IntPrompt.ask(message, default=default, choices=choices))
        answer = self.prompt(message, default=str(default), choices=choices)
        return int(answer)

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
