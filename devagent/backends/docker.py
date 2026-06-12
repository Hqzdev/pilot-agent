"""Docker sandbox backend for running agent commands in a session container."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from devagent.backends.base import BackendCheckResult, ExecResult, ExecutionBackend, ProcessHandle
from devagent.backends.local import ensure_command_allowed


class DockerProcessHandle(ProcessHandle):
    def __init__(self, backend: DockerBackend, ident: str):
        self.backend = backend
        self.ident = ident
        self.log_path = f"/tmp/devagent-{ident}.log"
        self.pid_path = f"/tmp/devagent-{ident}.pid"
        self.exit_path = f"/tmp/devagent-{ident}.exit"

    def poll(self) -> int | None:
        code = self.backend._exec_raw(
            f"test -f {self.exit_path} && cat {self.exit_path}",
            timeout_s=2,
        )
        if code.exit_code != 0 or not code.output.strip():
            return None
        try:
            return int(code.output.strip().splitlines()[-1])
        except ValueError:
            return 1

    def output_tail(self, lines: int = 50) -> str:
        result = self.backend._exec_raw(
            f"test -f {self.log_path} && tail -n {lines} {self.log_path} || true",
            timeout_s=5,
        )
        return result.output

    def terminate(self) -> None:
        self.backend._exec_raw(
            "if test -f "
            f"{self.pid_path}; then kill -TERM -$(cat {self.pid_path}) 2>/dev/null || true; fi",
            timeout_s=5,
        )
        time.sleep(3)
        self.backend._exec_raw(
            "if test -f "
            f"{self.pid_path}; then kill -KILL -$(cat {self.pid_path}) 2>/dev/null || true; fi",
            timeout_s=5,
        )

    def probe_http(self, url: str, expect_status: int) -> int | None:
        quoted = shlex.quote(url)
        result = self.backend._exec_raw(
            f"curl -sS -o /dev/null -w '%{{http_code}}' --max-time 5 {quoted}",
            timeout_s=8,
        )
        if result.exit_code != 0:
            return None
        try:
            status = int(result.output.strip()[-3:])
        except ValueError:
            return None
        return status if status == expect_status else status


class DockerBackend(ExecutionBackend):
    name = "docker"

    def __init__(
        self,
        *,
        project_root: Path,
        image: str = "devagent-sandbox:latest",
        network: str = "bridge",
        session_id: str | None = None,
    ):
        self.project_root = project_root.resolve()
        self.image = image
        self.network = network
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.container_name = f"devagent-sbx-{self.session_id}"
        self._started = False

    def exec(
        self,
        command: str,
        cwd: str,
        timeout_s: int,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        del cwd
        ensure_command_allowed(command)
        env_prefix = ""
        if env:
            env_prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " "
        return self._exec_raw(f"cd /workspace && {env_prefix}{command}", timeout_s=timeout_s)

    def spawn(self, command: str, cwd: str) -> ProcessHandle:
        del cwd
        ensure_command_allowed(command)
        self._ensure_started()
        ident = uuid.uuid4().hex[:12]
        handle = DockerProcessHandle(self, ident)
        quoted = shlex.quote(command)
        start = (
            f"cd /workspace && "
            f"nohup setsid bash -lc {quoted} > {handle.log_path} 2>&1 & "
            f"echo $! > {handle.pid_path}; "
            f"( wait $(cat {handle.pid_path}); echo $? > {handle.exit_path} ) >/dev/null 2>&1 &"
        )
        self._exec_raw(start, timeout_s=5)
        return handle

    def healthcheck(self) -> BackendCheckResult:
        if not _docker_available():
            return BackendCheckResult(
                "fail",
                "backend docker",
                "docker daemon unavailable",
                "Install/start Docker or run: devagent backend local",
            )
        image = subprocess.run(
            ["docker", "image", "inspect", self.image],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if image.returncode != 0:
            return BackendCheckResult(
                "fail",
                "sandbox image",
                f"{self.image} not built",
                "Run: devagent sandbox build",
            )
        probe = self.exec("echo ok", "/workspace", 2)
        if probe.exit_code == 0 and "ok" in probe.output:
            return BackendCheckResult("pass", "backend docker", f"{self.image} ready")
        return BackendCheckResult("fail", "backend docker", probe.output, "Run: devagent doctor")

    def cleanup(self) -> None:
        if self._started:
            subprocess.run(
                ["docker", "rm", "-f", self.container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            self._started = False

    def _ensure_started(self) -> None:
        if self._started:
            return
        existing = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", self.container_name],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if existing.stdout.strip() == "true":
            self._started = True
            return
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            self.container_name,
            "-v",
            f"{self.project_root}:/workspace",
            "-w",
            "/workspace",
            "--network",
            self.network,
            self.image,
            "sleep",
            "infinity",
        ]
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout.strip())
        self._started = True

    def _exec_raw(self, command: str, *, timeout_s: int) -> ExecResult:
        self._ensure_started()
        start = time.monotonic()
        proc = subprocess.run(
            ["docker", "exec", self.container_name, "bash", "-lc", command],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_s,
            check=False,
        )
        return ExecResult(proc.returncode, proc.stdout or "", time.monotonic() - start)


def _docker_available() -> bool:
    if not os.environ.get("PATH"):
        return False
    result = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0
