from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pilot_agent.backends.base import ExecutionBackend
from pilot_agent.backends.local import LocalBackend
from pilot_agent.tools.base import Tool


class RunAndCheckTool(Tool):
    name = "run_and_check"
    description = (
        "Run a long-lived command, optionally probe HTTP, terminate it, and return JSON verdict."
    )
    timeout_s = 240
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "wait_s": {"type": "integer", "minimum": 0, "default": 8},
            "http_probe": {"type": "string"},
            "expect_status": {"type": "integer", "default": 200},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def __init__(self, project_root: Path, backend: ExecutionBackend | None = None):
        self.project_root = project_root.resolve()
        self.backend = backend or LocalBackend()

    def execute(self, **kwargs: Any) -> str:
        command = str(kwargs["command"])
        wait_s = int(kwargs.get("wait_s", 8))
        http_probe = kwargs.get("http_probe")
        typed_probe = str(http_probe) if http_probe is not None else None
        expect_status = int(kwargs.get("expect_status", 200))
        handle = self.backend.spawn(command, cwd=str(self.project_root))
        time.sleep(wait_s)
        output = handle.output_tail()
        exit_code = handle.poll()
        if exit_code is not None:
            return json.dumps(
                {
                    "started": False,
                    "exit_code": exit_code,
                    "stderr_tail": self._tail(output),
                    "verdict": "fail",
                }
            )
        http_status: int | None = None
        if typed_probe:
            for _ in range(3):
                http_status = handle.probe_http(typed_probe, expect_status)
                if http_status == expect_status:
                    break
                time.sleep(2)
        handle.terminate()
        verdict = "pass" if typed_probe is None or http_status == expect_status else "fail"
        return json.dumps(
            {
                "started": True,
                "http_status": http_status,
                "stderr_tail": self._tail(output + "\n" + handle.output_tail()),
                "verdict": verdict,
            }
        )

    @staticmethod
    def _tail(output: str) -> str:
        return "\n".join(output.splitlines()[-50:])
