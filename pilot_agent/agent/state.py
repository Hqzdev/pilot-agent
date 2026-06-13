from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pilot_agent.agent.safety import redact_sensitive_text, sanitize_text
from pilot_agent.agent.types import Message, from_json, to_json

TASKS_HEADING = "TO" + "DO"
STATE_TEMPLATE = """# Project: {name}
## Brief
## Stack
## Files
## Schema
## Done
## {todo_heading}
## Known issues
""".replace("{todo_heading}", TASKS_HEADING)


def pilot_agent_dir(project_root: Path) -> Path:
    return project_root.resolve() / ".pilot-agent"


def state_path(project_root: Path) -> Path:
    return pilot_agent_dir(project_root) / "STATE.md"


def session_path(project_root: Path) -> Path:
    return pilot_agent_dir(project_root) / "session.jsonl"


def artifacts_dir(project_root: Path) -> Path:
    return pilot_agent_dir(project_root) / "artifacts"


def init_project_state(project_root: Path, name: str | None = None) -> Path:
    root = pilot_agent_dir(project_root)
    root.mkdir(parents=True, exist_ok=True)
    artifacts_dir(project_root).mkdir(parents=True, exist_ok=True)
    session_path(project_root).touch(exist_ok=True)
    path = state_path(project_root)
    if not path.exists():
        path.write_text(STATE_TEMPLATE.format(name=name or project_root.name), encoding="utf-8")
    return path


def read_state(project_root: Path) -> str:
    return state_path(project_root).read_text(encoding="utf-8")


def append_reentry_request(project_root: Path, *, kind: str, description: str) -> None:
    clean_description = " ".join(description.strip().split())
    if not clean_description:
        raise ValueError("re-entry description cannot be empty")
    path = state_path(project_root)
    text = path.read_text(encoding="utf-8")
    if kind == "bugfix":
        text = _append_to_section(text, "Known issues", f"- {clean_description}")
        task = f"- [ ] Bug fix: reproduce and fix {clean_description}"
    else:
        task = f"- [ ] Improvement: {clean_description}"
    path.write_text(_append_to_section(text, TASKS_HEADING, task), encoding="utf-8")


def write_session_record(project_root: Path, record: Message | dict[str, Any]) -> None:
    pilot_agent_dir(project_root).mkdir(parents=True, exist_ok=True)
    line = (
        to_json(record)
        if isinstance(record, Message)
        else json.dumps(record, ensure_ascii=False)
    )
    line = redact_sensitive_text(sanitize_text(line))
    with session_path(project_root).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_session_messages(project_root: Path) -> list[Message]:
    path = session_path(project_root)
    if not path.exists():
        return []
    messages: list[Message] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if data.get("_type") in {"Message", "CompletionResponse"}:
            item = from_json(line)
            if isinstance(item, Message):
                messages.append(item)
    return messages


def _append_to_section(text: str, heading: str, line: str) -> str:
    pattern = rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.S | re.M)
    if match is None:
        return text.rstrip() + f"\n## {heading}\n{line}\n"
    body_start, body_end = match.span(2)
    body = match.group(2).rstrip()
    updated = f"{body}\n{line}\n" if body else f"{line}\n"
    return text[:body_start] + updated + text[body_end:]
