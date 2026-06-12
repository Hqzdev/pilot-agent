from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

from pilot_agent.agent.types import Message, Role, ToolCall, ToolResult

LessonSummarizer = Callable[[str], str]

DEPLOY_SYNTHESIS_PROMPT = (
    "The deploy phase is complete. Review the work. Is there a reusable procedure\n"
    "(sequence of commands/edits) that is not already covered by loaded skills and\n"
    "would help in other projects? If yes, call save_skill with a standard skill\n"
    "format skill (frontmatter: source: learned). If not, call\n"
    "complete_phase."
)

LESSON_PROMPT = """Extract a lesson from this fix cycle.
Error: {stderr_tail}
Actions: {actions}
Strict response format:
PROBLEM: one line
FIX: 1-3 lines with concrete commands/edits
TAGS: 2-4 stack tags, comma-separated
If the lesson is trivial (typo, forgotten import) or specific only to this
project, answer with one word: SKIP"""


class SkillOutcomeRecorder(Protocol):
    def record_outcome(self, name: str, success: bool) -> None: ...


@dataclass
class PendingRun:
    key: str
    command: str
    stderr_tail: str
    actions: list[str] = field(default_factory=list)


class Memory:
    def __init__(
        self,
        home: Path | None = None,
        *,
        summarizer: LessonSummarizer | None = None,
        skill_recorder: SkillOutcomeRecorder | None = None,
    ):
        self.home = home or _default_home()
        self.lessons_path = self.home / "lessons.md"
        self.summarizer = summarizer
        self.skill_recorder = skill_recorder
        self._pending: dict[str, PendingRun] = {}
        self._failed_skill_keys: set[tuple[str, str]] = set()

    def observe(self, call: ToolCall, result: ToolResult) -> None:
        for pending in self._pending.values():
            if not _is_matching_run_observation(call, pending.key):
                pending.actions.append(_action_summary(call))
        if call.name != "run_and_check" or result.is_error:
            return
        data = _result_json(result)
        verdict = data.get("verdict")
        key = _run_key(call)
        if not key:
            return
        if verdict == "fail":
            self._pending[key] = PendingRun(
                key=key,
                command=str(call.arguments.get("command", "")),
                stderr_tail=str(data.get("stderr_tail", "")),
            )
        elif verdict == "pass" and key in self._pending:
            pending = self._pending.pop(key)
            self._record_lesson(pending)

    def relevant_lessons(self, stack: list[str], limit: int = 10) -> str:
        if not self.lessons_path.exists():
            return ""
        stack_set = {item.lower() for item in stack}
        entries = _parse_lessons(self.lessons_path.read_text(encoding="utf-8"))
        matches = [
            entry
            for entry in entries
            if stack_set and stack_set.intersection({tag.lower() for tag in entry.tags})
        ]
        return "\n\n".join(entry.text for entry in list(reversed(matches))[:limit])

    def end_of_phase(self, phase: str, history: list[Message]) -> None:
        if phase != "deploy" or _has_deploy_synthesis_prompt(history):
            return
        history.append(
            Message(
                role=Role.USER,
                content=DEPLOY_SYNTHESIS_PROMPT,
                pinned=True,
                phase=phase,
            )
        )

    def end_of_session(self, history: list[Message]) -> None:
        if self.skill_recorder is None:
            return
        loaded: set[tuple[str, str]] = set()
        completed_phases: set[str] = set()
        for message in history:
            if message.role is not Role.ASSISTANT:
                continue
            phase = message.phase or "unknown"
            for call in message.tool_calls:
                if call.name == "load_skill":
                    name = str(call.arguments.get("name", ""))
                    if name:
                        loaded.add((phase, name))
                elif call.name == "complete_phase":
                    completed_phases.add(phase)
        for phase, name in sorted(loaded):
            key = (phase, name)
            if phase not in completed_phases and key not in self._failed_skill_keys:
                self.skill_recorder.record_outcome(name, False)
                self._failed_skill_keys.add(key)

    def _record_lesson(self, pending: PendingRun) -> None:
        if self.summarizer is None:
            return
        actions = "\n".join(f"- {action}" for action in pending.actions) or "- no actions observed"
        prompt = LESSON_PROMPT.format(stderr_tail=pending.stderr_tail, actions=actions)
        lesson = self.summarizer(prompt).strip()
        if lesson == "SKIP":
            return
        parsed = _parse_lesson_response(lesson)
        if parsed is None:
            return
        problem, fix, tags = parsed
        self.home.mkdir(parents=True, exist_ok=True)
        with self.lessons_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"## [{date.today().isoformat()}] tags: {', '.join(tags)}\n"
                f"PROBLEM: {problem}\n"
                f"FIX: {fix}\n\n"
            )


@dataclass
class LessonEntry:
    tags: list[str]
    text: str


def _default_home() -> Path:
    return Path(os.environ.get("PILOT_AGENT_HOME", "~/.pilot-agent")).expanduser()


def _result_json(result: ToolResult) -> dict[str, object]:
    try:
        data = json.loads(result.content)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _run_key(call: ToolCall) -> str | None:
    command = str(call.arguments.get("command", ""))
    executable = _executable(command)
    if not executable:
        return None
    probe = str(call.arguments.get("http_probe", ""))
    port = _port(command) or _port(probe)
    return f"{executable}:{port or ''}"


def _executable(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    return Path(parts[0]).name if parts else ""


def _port(value: str) -> str | None:
    explicit = re.search(r"(?:--port|PORT=)\s*=?\s*(\d+)", value)
    if explicit:
        return explicit.group(1)
    url = re.search(r":(\d+)(?:/|\b)", value)
    return url.group(1) if url else None


def _is_matching_run_observation(call: ToolCall, key: str) -> bool:
    return call.name == "run_and_check" and _run_key(call) == key


def _action_summary(call: ToolCall) -> str:
    return f"{call.name} {json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)}"


def _parse_lesson_response(text: str) -> tuple[str, str, list[str]] | None:
    if not text.startswith("PROBLEM:"):
        return None
    problem_match = re.search(r"^PROBLEM:\s*(.+)$", text, flags=re.M)
    fix_match = re.search(r"^FIX:\s*(.+?)(?=^TAGS:|\Z)", text, flags=re.S | re.M)
    tags_match = re.search(r"^TAGS:\s*(.+)$", text, flags=re.M)
    if not problem_match or not fix_match or not tags_match:
        return None
    tags = [tag.strip() for tag in tags_match.group(1).split(",") if tag.strip()]
    if not tags:
        return None
    fix = " ".join(line.strip() for line in fix_match.group(1).splitlines() if line.strip())
    return problem_match.group(1).strip(), fix, tags


def _parse_lessons(text: str) -> list[LessonEntry]:
    entries: list[LessonEntry] = []
    pattern = re.compile(r"(^## \[[^\]]+\] tags:\s*(.*?)\n.*?)(?=^## |\Z)", re.S | re.M)
    for match in pattern.finditer(text):
        tags = [tag.strip() for tag in match.group(2).split(",") if tag.strip()]
        entries.append(LessonEntry(tags=tags, text=match.group(1).strip()))
    return entries


def _has_deploy_synthesis_prompt(history: list[Message]) -> bool:
    return any(message.content.startswith("The deploy phase is complete.") for message in history)
