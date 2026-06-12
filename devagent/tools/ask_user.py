from __future__ import annotations

from typing import Any

from devagent.cli.ui.input import DevAgentInput
from devagent.tools.base import Tool


class AskUserTool(Tool):
    name = "ask_user"
    description = "Ask the user a blocking terminal question and return their answer."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "choices": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["question"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs: Any) -> str:
        question = str(kwargs["question"])
        choices = kwargs.get("choices")
        typed_choices = [str(choice) for choice in choices] if isinstance(choices, list) else None
        return DevAgentInput().prompt(question, choices=typed_choices)
