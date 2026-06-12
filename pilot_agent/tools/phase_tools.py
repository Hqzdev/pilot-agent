from __future__ import annotations

from typing import Any

from pilot_agent.tools.base import Tool


class CompletePhaseTool(Tool):
    name = "complete_phase"
    description = (
        "Mark the current phase complete with a summary for STATE.md and advance the pipeline."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs: Any) -> str:
        summary = str(kwargs["summary"])
        return summary
