from __future__ import annotations

import os
from pathlib import Path

from any2md.errors import OutputLockError
from any2md.io_state import output_lock_path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class OutputFileLock:
    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path
        self._lock_path = output_lock_path(output_path)
        self._handle = None

    def __enter__(self) -> "OutputFileLock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._lock_path.open("a+", encoding="utf-8")
        self._handle.seek(0)
        if not self._handle.read(1):
            self._handle.write("0")
            self._handle.flush()
        self._handle.seek(0)

        try:
            if os.name == "nt":
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            self._handle = None
            raise OutputLockError(f"Output is locked by another any2md process: {self._output_path}") from exc

        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(str(os.getpid()))
        self._handle.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is None:
            return

        try:
            self._handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
