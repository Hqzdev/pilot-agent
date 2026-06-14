from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

from pilot_agent.agent.state import pilot_agent_dir

_ACTIVE_LOCKS: set[Path] = set()


class ProjectSessionLock:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.path = pilot_agent_dir(self.project_root) / "session.lock"
        self._fh: BinaryIO | None = None

    def __enter__(self) -> ProjectSessionLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        resolved_lock = self.path.resolve()
        if resolved_lock in _ACTIVE_LOCKS:
            raise RuntimeError(
                "Another Pilot Agent session is already running for this project. "
                "Stop it or remove .pilot-agent/session.lock if the process is gone."
            )
        fh = self.path.open("a+b")
        self._fh = fh
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            self._fh = None
            raise RuntimeError(
                "Another Pilot Agent session is already running for this project. "
                "Stop it or remove .pilot-agent/session.lock if the process is gone."
            ) from exc
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()).encode())
        fh.flush()
        _ACTIVE_LOCKS.add(resolved_lock)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
            self._fh = None
            _ACTIVE_LOCKS.discard(self.path.resolve())
