from __future__ import annotations

from typing import Any, Protocol

from pilot_agent.tools.base import Tool


class SkillBackend(Protocol):
    def load(self, name: str) -> str: ...

    def save(self, content: str) -> object: ...


class LoadSkillTool(Tool):
    name = "load_skill"
    parallel_safe = True
    description = "Load the full markdown for a named skill before using that procedure."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }

    def __init__(self, backend: SkillBackend):
        self.backend = backend

    def execute(self, **kwargs: Any) -> str:
        name = str(kwargs["name"])
        return self.backend.load(name)


class SaveSkillTool(Tool):
    name = "save_skill"
    description = (
        "Persist a learned skill markdown document after a reusable procedure is discovered."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
        "additionalProperties": False,
    }

    def __init__(self, backend: SkillBackend):
        self.backend = backend

    def execute(self, **kwargs: Any) -> str:
        content = str(kwargs["content"])
        return str(self.backend.save(content))
