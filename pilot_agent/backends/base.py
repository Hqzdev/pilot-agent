"""Backend contracts for local and sandboxed command execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

BackendStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    output: str
    duration_s: float


@dataclass(frozen=True)
class BackendCheckResult:
    status: BackendStatus
    name: str
    details: str
    fix: str | None = None


class ProcessHandle(ABC):
    @abstractmethod
    def poll(self) -> int | None: ...

    @abstractmethod
    def output_tail(self, lines: int = 50) -> str: ...

    @abstractmethod
    def terminate(self) -> None: ...

    def probe_http(self, url: str, expect_status: int) -> int | None:
        del url, expect_status
        return None


class ExecutionBackend(ABC):
    name: str

    @abstractmethod
    def exec(
        self,
        command: str,
        cwd: str,
        timeout_s: int,
        env: dict[str, str] | None = None,
    ) -> ExecResult: ...

    @abstractmethod
    def spawn(self, command: str, cwd: str) -> ProcessHandle: ...

    @abstractmethod
    def healthcheck(self) -> BackendCheckResult: ...

    def cleanup(self) -> None:
        return None

    def as_tool_context(self) -> dict[str, Any]:
        return {"backend": self.name}
