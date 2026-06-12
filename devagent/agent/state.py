from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devagent.agent.types import Message, from_json, to_json

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


def devagent_dir(project_root: Path) -> Path:
    return project_root.resolve() / ".devagent"


def state_path(project_root: Path) -> Path:
    return devagent_dir(project_root) / "STATE.md"


def session_path(project_root: Path) -> Path:
    return devagent_dir(project_root) / "session.jsonl"


def artifacts_dir(project_root: Path) -> Path:
    return devagent_dir(project_root) / "artifacts"


def init_project_state(project_root: Path, name: str | None = None) -> Path:
    root = devagent_dir(project_root)
    root.mkdir(parents=True, exist_ok=True)
    artifacts_dir(project_root).mkdir(parents=True, exist_ok=True)
    session_path(project_root).touch(exist_ok=True)
    path = state_path(project_root)
    if not path.exists():
        path.write_text(STATE_TEMPLATE.format(name=name or project_root.name), encoding="utf-8")
    return path


def read_state(project_root: Path) -> str:
    return state_path(project_root).read_text(encoding="utf-8")


def write_session_record(project_root: Path, record: Message | dict[str, Any]) -> None:
    devagent_dir(project_root).mkdir(parents=True, exist_ok=True)
    line = (
        to_json(record)
        if isinstance(record, Message)
        else json.dumps(record, ensure_ascii=False)
    )
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
