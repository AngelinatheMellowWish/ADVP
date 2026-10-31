"""Single-writer instance lock for the local data directory."""

from __future__ import annotations

import contextlib
import errno
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import IO, Any

if sys.platform == "win32":
    import msvcrt

_LOCK_CONTENTION_ERRNOS = {errno.EACCES, errno.EDEADLK}


def _is_lock_contention(exc: OSError) -> bool:
    return exc.errno in _LOCK_CONTENTION_ERRNOS or getattr(exc, "winerror", None) == 33


def _lock_posix(handle: IO[bytes]) -> None:
    fcntl: Any = importlib.import_module("fcntl")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_posix(handle: IO[bytes]) -> None:
    fcntl: Any = importlib.import_module("fcntl")
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class InstanceLock:
    """Hold an OS-level lock so only one process writes to a data directory."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._handle: IO[bytes] | None = None
        self._locked = False
        self._read_only = False

    @property
    def read_only(self) -> bool:
        """Whether acquisition failed because another instance owns the lock."""
        return self._read_only

    def acquire(self) -> bool:
        """Try to take the lock without blocking."""
        if self._locked:
            return True
        self._read_only = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if sys.platform == "win32":
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    if not _is_lock_contention(exc):
                        raise
                    self._enter_read_only(handle)
                    return False
            else:
                try:
                    _lock_posix(handle)
                except BlockingIOError:
                    self._enter_read_only(handle)
                    return False
            self._handle = handle
            self._locked = True
            return True
        except BaseException:
            with contextlib.suppress(OSError):
                handle.close()
            raise

    def _enter_read_only(self, handle: IO[bytes]) -> None:
        with contextlib.suppress(OSError):
            handle.close()
        self._read_only = True
        logging.getLogger("advp").warning(
            "instance_lock_contended",
            extra={"lock_path": str(self.path)},
        )

    def release(self) -> None:
        """Unlock and close the lock file, tolerating partial acquisition."""
        handle = self._handle
        self._handle = None
        was_locked = self._locked
        self._locked = False
        if handle is None:
            return
        try:
            if was_locked:
                if sys.platform == "win32":
                    handle.seek(0)
                    with contextlib.suppress(OSError):
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    with contextlib.suppress(OSError):
                        _unlock_posix(handle)
        finally:
            handle.close()
