from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from devagent.tools.base import Tool

BLOCKLIST = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\brm\s+-rf\s+/",
        r"\brm\s+-rf\s+~",
        r"\bsudo\b",
        r"\bmkfs\b",
        r":\(\)\{\s*:\|:&\s*\};:",
        r">\s*/etc/",
        r">\s*/usr/",
    ]
]


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

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def execute(self, **kwargs: Any) -> str:
        command = str(kwargs["command"])
        timeout_s = int(kwargs.get("timeout_s", 120))
        for pattern in BLOCKLIST:
            if pattern.search(command):
                raise ValueError(f"blocked dangerous command pattern: {pattern.pattern}")
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        try:
            proc = subprocess.run(
                command,
                cwd=self.project_root,
                env=env,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
                check=False,
            )
            output = proc.stdout or ""
            return f"[exit {proc.returncode}]\n{output}"
        except subprocess.TimeoutExpired as exc:
            raw_output = exc.stdout or ""
            output = (
                raw_output.decode(errors="replace")
                if isinstance(raw_output, bytes)
                else raw_output
            )
            return f"[exit timeout]\ncommand timed out after {timeout_s}s\n{output}"
