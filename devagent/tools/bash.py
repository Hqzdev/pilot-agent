from __future__ import annotations

from pathlib import Path
from typing import Any

from devagent.backends.base import ExecutionBackend
from devagent.backends.local import LocalBackend
from devagent.tools.base import Tool


class BashTool(Tool):
    name = "bash"
    description = "Run a shell command in the project root and return combined stdout/stderr."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout_s": {"type": "integer", "minimum": 1, "default": 120},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def __init__(self, project_root: Path, backend: ExecutionBackend | None = None):
        self.project_root = project_root.resolve()
        self.backend = backend or LocalBackend()

    def execute(self, **kwargs: Any) -> str:
        command = str(kwargs["command"])
        timeout_s = int(kwargs.get("timeout_s", 120))
        result = self.backend.exec(
            command,
            cwd=str(self.project_root),
            timeout_s=timeout_s,
            env={"NO_COLOR": "1"},
        )
        return f"[exit {result.exit_code}]\n{result.output}"
