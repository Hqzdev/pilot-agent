from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from pilot_agent.agent.state import pilot_agent_dir

_ACTIVE_LOCKS: set[Path] = set()


class ProjectSessionLock:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.path = pilot_agent_dir(self.project_root) / "session.lock"
        self._fh = None

    def __enter__(self) -> ProjectSessionLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        resolved_lock = self.path.resolve()
        if resolved_lock in _ACTIVE_LOCKS:
            raise RuntimeError(
                "Another Pilot Agent session is already running for this project. "
                "Stop it or remove .pilot-agent/session.lock if the process is gone."
            )
        self._fh = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._fh.close()
            self._fh = None
            raise RuntimeError(
                "Another Pilot Agent session is already running for this project. "
                "Stop it or remove .pilot-agent/session.lock if the process is gone."
            ) from exc
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()).encode())
        self._fh.flush()
        _ACTIVE_LOCKS.add(resolved_lock)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None
            _ACTIVE_LOCKS.discard(self.path.resolve())
