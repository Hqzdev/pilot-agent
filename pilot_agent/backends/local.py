"""Local command backend; fast but intentionally not isolated."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

import requests

from pilot_agent.backends.base import (
    BackendCheckResult,
    ExecResult,
    ExecutionBackend,
    ProcessHandle,
)

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


def ensure_command_allowed(command: str) -> None:
    for pattern in BLOCKLIST:
        if pattern.search(command):
            raise ValueError(f"blocked dangerous command pattern: {pattern.pattern}")


class LocalProcessHandle(ProcessHandle):
    def __init__(self, proc: subprocess.Popen[str]):
        self.proc = proc
        self._buffer = ""

    def poll(self) -> int | None:
        return self.proc.poll()

    def output_tail(self, lines: int = 50) -> str:
        if self.proc.stdout is not None and self.proc.poll() is not None:
            with suppress(ValueError):
                self._buffer += self.proc.stdout.read()
        return "\n".join(self._buffer.splitlines()[-lines:])

    def terminate(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            with suppress(ProcessLookupError):
                os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=3)

    def probe_http(self, url: str, expect_status: int) -> int | None:
        try:
            status = requests.get(url, timeout=5).status_code
        except requests.RequestException:
            return None
        return status if status == expect_status else status


class LocalBackend(ExecutionBackend):
    name = "local"

    def exec(
        self,
        command: str,
        cwd: str,
        timeout_s: int,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        ensure_command_allowed(command)
        merged_env = os.environ.copy()
        merged_env["NO_COLOR"] = "1"
        if env:
            merged_env.update(env)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=Path(cwd),
                env=merged_env,
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
                check=False,
            )
            return ExecResult(proc.returncode, proc.stdout or "", time.monotonic() - start)
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            return ExecResult(
                124,
                f"command timed out after {timeout_s}s\n{output}",
                time.monotonic() - start,
            )

    def spawn(self, command: str, cwd: str) -> ProcessHandle:
        ensure_command_allowed(command)
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        proc = subprocess.Popen(
            command,
            cwd=Path(cwd),
            env=env,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )
        return LocalProcessHandle(proc)

    def healthcheck(self) -> BackendCheckResult:
        return BackendCheckResult(
            "warn",
            "backend local",
            "commands run directly on this machine",
            "Run: pilot-agent backend docker",
        )
