"""Single instance: only one HyperGet runs per user (per HYPEGET_HOME).

The first copy holds an OS-level lock on ``instance.lock``. A second copy can't
take the lock, so it asks the running one to show its window (and optionally
run a command such as "add") and exits, like IDM.

The OS releases the lock automatically if HyperGet crashes, so a stale lock
file never blocks the next start.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from .config import app_home


class SingleInstance:
    def __init__(self, home: str | None = None):
        self.path = os.path.join(home or app_home(), "instance.lock")
        self._fh = None

    def acquire(self) -> bool:
        """True if this process is now the only HyperGet."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fh = open(self.path, "a+b")  # noqa: SIM115 - held open for the app's lifetime
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()).encode())
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        if not self._fh:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._fh.close()
        self._fh = None


def ask_running_app(command: str = "show", home: str | None = None, wait: float = 10.0) -> bool:
    """Tell the HyperGet that holds the lock to show itself (and run ``command``).

    The other copy may have only just started, so retry until its API is up.
    """
    runtime = os.path.join(home or app_home(), "runtime.json")
    end = time.monotonic() + wait
    while True:
        try:
            with open(runtime, encoding="utf-8") as f:
                port = int(json.load(f)["port"])
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/app/show", method="POST",
                data=json.dumps({"command": command}).encode(),
                headers={"X-HyperGet": "1", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status == 200
        except (OSError, ValueError, KeyError):
            if time.monotonic() > end:
                return False
            time.sleep(0.25)
