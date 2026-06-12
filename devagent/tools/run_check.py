from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import requests

from devagent.tools.base import Tool


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

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def execute(self, **kwargs: Any) -> str:
        command = str(kwargs["command"])
        wait_s = int(kwargs.get("wait_s", 8))
        http_probe = kwargs.get("http_probe")
        typed_probe = str(http_probe) if http_probe is not None else None
        expect_status = int(kwargs.get("expect_status", 200))
        proc = subprocess.Popen(
            command,
            cwd=self.project_root,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )
        time.sleep(wait_s)
        output = self._drain(proc)
        if proc.poll() is not None:
            return json.dumps(
                {
                    "started": False,
                    "exit_code": proc.returncode,
                    "stderr_tail": self._tail(output),
                    "verdict": "fail",
                }
            )
        http_status: int | None = None
        if typed_probe:
            for _ in range(3):
                try:
                    http_status = requests.get(typed_probe, timeout=5).status_code
                    if http_status == expect_status:
                        break
                except requests.RequestException:
                    http_status = None
                time.sleep(2)
        self._terminate_group(proc)
        verdict = "pass" if typed_probe is None or http_status == expect_status else "fail"
        return json.dumps(
            {
                "started": True,
                "http_status": http_status,
                "stderr_tail": self._tail(output + self._drain(proc)),
                "verdict": verdict,
            }
        )

    @staticmethod
    def _drain(proc: subprocess.Popen[str]) -> str:
        if proc.stdout is None:
            return ""
        try:
            return proc.stdout.read() if proc.poll() is not None else ""
        except ValueError:
            return ""

    @staticmethod
    def _tail(output: str) -> str:
        return "\n".join(output.splitlines()[-50:])

    @staticmethod
    def _terminate_group(proc: subprocess.Popen[str]) -> None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=3)
